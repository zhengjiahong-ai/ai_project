import os
import uuid
import PyPDF2
import docx
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings

# ====================== 核心配置（可根据需求调整） ======================
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"  # 学术场景可换为"allenai/scibert_scivocab_uncased"
CHROMA_DB_PATH = os.environ.get(
    "CHROMA_DB_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_literature_db")
)  # 向量库存储路径（相对ai-service-python目录）
CHUNK_SIZE = 500  # 文献分段长度
CHUNK_OVERLAP = 50  # 分段重叠长度


# ====================== RAG核心类 ======================
class LiteratureRAG:
    def __init__(self):
        # 初始化Embedding模型
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        # 初始化Chroma向量数据库（持久化存储）
        self.chroma_client = chromadb.PersistentClient(
            path=CHROMA_DB_PATH,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        # 创建/获取文献集合
        self.collection = self.chroma_client.get_or_create_collection(
            name="literature_collection",
            metadata={
                "description": "AI文献助手-学术文献向量库",
                "hnsw:space": "cosine"
            }
        )

    # 文献解析（基础层能力）
    def parse_literature(self, file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文献文件不存在：{file_path}")

        text = ""
        if file_path.endswith(".pdf"):
            with open(file_path, "rb") as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        elif file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                if para.text:
                    text += para.text + "\n"
        else:
            raise ValueError("仅支持.pdf/.docx格式的文献")

        return text.strip()

    # 文本分段（适配学术文献）
    def split_text(self, text):
        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = start + CHUNK_SIZE
            if end < text_len:
                end = text.rfind(".", start, end) + 1 or text.rfind("\n", start, end) + 1 or end
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            new_start = end - CHUNK_OVERLAP
            if new_start <= start:
                break
            start = new_start
        return chunks

    # 向量入库
    def add_literature_to_db(self, file_path, literature_metadata=None):
        raw_text = self.parse_literature(file_path)
        if not raw_text:
            raise ValueError(f"文献解析后无有效文本：{file_path}")

        text_chunks = self.split_text(raw_text)
        if not text_chunks:
            raise ValueError(f"文献分段后无有效内容：{file_path}")

        embeddings = self.embedding_model.encode(
            text_chunks,
            normalize_embeddings=True
        ).tolist()
        ids = [str(uuid.uuid4()) for _ in text_chunks]

        metadata = literature_metadata or {}
        metadata["file_name"] = os.path.basename(file_path)
        metadatas = [
            {**metadata, "chunk_index": idx}
            for idx in range(len(text_chunks))
        ]

        self.collection.add(
            ids=ids,
            documents=text_chunks,
            embeddings=embeddings,
            metadatas=metadatas
        )

        return len(text_chunks)

    # 向量检索（支撑交互层/深度分析层）
    def retrieve(self, query, top_k=5, filter_metadata=None):
        query_embedding = self.embedding_model.encode(
            query,
            normalize_embeddings=True
        ).tolist()

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata,
            include=["documents", "distances", "metadatas"]
        )
        if not results or not results.get("documents") or not results["documents"][0]:
            return []

        formatted_results = []
        docs = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        formatted_results = []

        for i in range(min(len(docs), top_k)):
            distance = distances[i]

            # 若为cosine distance
            similarity = 1 - distance

            similarity = max(min(similarity, 1.0), 0.0)

            formatted_results.append({
                "text": docs[i],
                "similarity": similarity,
                "metadata": metas[i]
            })

        return formatted_results

    # 辅助功能
    def reset_db(self):
        self.chroma_client.delete_collection("literature_collection")
        self.collection = self.chroma_client.create_collection(
            name="literature_collection",
            metadata={"description": "AI文献助手-学术文献向量库"}
        )

    def get_db_stats(self):
        return self.collection.count()