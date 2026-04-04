import os
import uuid
import shutil
import tempfile

import chromadb
from chromadb.config import Settings

from sentence_transformers import SentenceTransformer

from grobid_client.grobid_client import GrobidClient

from core.document_parser import parse_tei_xml
from core.smart_chunker import chunk_sections


EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

CHROMA_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "chroma_literature_db"
)


class LiteratureRAG:
    @staticmethod
    def normalize_id(id_str):
        """ 归一化 ID，去除特殊字符，防止编码不一致导致的检索失败 """
        if not id_str: return "unknown"
        # 只保留字母、数字、下划线、点、横杠
        import re
        clean_id = re.sub(r'[^a-zA-Z0-9.\-_]', '_', str(id_str))
        return clean_id.lower()

    def __init__(self):

        self.embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )

        self.chroma_client = chromadb.PersistentClient(
            path=CHROMA_DB_PATH,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        self.collection = self.chroma_client.get_or_create_collection(
            name="literature_collection_v3", # 👈 再次升级名称以强制重置
            metadata={
                "hnsw:space": "cosine"
            }
        )

    def parse_literature(self, file_path):

        input_dir = tempfile.mkdtemp()
        output_dir = tempfile.mkdtemp()

        try:

            shutil.copy(file_path, input_dir)

            grobid = GrobidClient(
                grobid_server="http://grobid:8070",
                batch_size=1
            )

            grobid.process(
                "processFulltextDocument",
                input_path=input_dir,
                output=output_dir
            )

            xml_files = [
                f for f in os.listdir(output_dir)
                if f.endswith(".tei.xml")
            ]

            if not xml_files:
                raise Exception("GROBID解析失败")

            tei_path = os.path.join(output_dir, xml_files[0])

            sections = parse_tei_xml(tei_path)

            return sections

        finally:
            shutil.rmtree(input_dir)
            shutil.rmtree(output_dir)

    def add_literature_to_db(self, file_path, literature_metadata=None):
        """ legacy method for backward compatibility """
        sections = self.parse_literature(file_path)
        return self.add_sections_to_db(sections, file_path, literature_metadata)

    def add_sections_to_db(self, sections, file_path, literature_metadata=None):
        """ New method: Accept already parsed sections to save time """
        metadata = literature_metadata or {}
        metadata["file_name"] = os.path.basename(file_path)

        chunks = chunk_sections(sections)
        
        # --- 核心改进：兜底逻辑 ---
        if not chunks:
            print(f"警告: 论文 {metadata['file_name']} 未提取到结构化章节，尝试全文聚合切分。")
            full_text = ""
            for sec in sections:
                if sec.get("content"):
                    full_text += f"\n{sec['content']}"
            
            if full_text.strip():
                fallback_sections = [{"section": "Full Text", "content": full_text}]
                chunks = chunk_sections(fallback_sections)
            
            if not chunks:
                print(f"致命警告: 论文 {metadata['file_name']} 彻底未提取到有效文本内容，跳过入库。")
                return 0
        
        # 归一化元数据中的 ID
        if "id" in metadata:
            metadata["id"] = self.normalize_id(metadata["id"])

        texts = [
            f"Paper: {metadata.get('title','unknown')}\n\nSection: {c['section']}\n\nContent:\n{c['text']}"
            for c in chunks
        ]

        embeddings = self.embedding_model.encode(
            texts,
            normalize_embeddings=True
        ).tolist()

        ids = [str(uuid.uuid4()) for _ in texts]

        metadatas = [
            {**metadata, "chunk_index": i}
            for i in range(len(texts))
        ]

        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas
        )

        return len(texts)

    def retrieve(self, query, top_k=5, filter_metadata=None):

        query_embedding = self.embedding_model.encode(
            query,
            normalize_embeddings=True
        ).tolist()

        # 归一化过滤条件中的 ID
        if filter_metadata and "id" in filter_metadata:
            filter_metadata["id"] = self.normalize_id(filter_metadata["id"])

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata,
            include=["documents", "distances", "metadatas"]
        )

        # 调试日志：检查是否真的查到了数据
        total_found = len(results.get("documents", [[]])[0])
        print(f"RAG 检索完成: 查询='{query[:30]}...', 匹配到 {total_found} 条片段")

        docs = results["documents"][0]
        dists = results["distances"][0]
        metas = results["metadatas"][0]

        output = []

        for i in range(len(docs)):

            similarity = 1 - dists[i]

            output.append({
                "text": docs[i],
                "similarity": similarity,
                "metadata": metas[i]
            })

        return output

    def get_documents_by_metadata(self, filter_metadata=None, limit=200):
        if filter_metadata and "id" in filter_metadata:
            filter_metadata["id"] = self.normalize_id(filter_metadata["id"])

        results = self.collection.get(
            where=filter_metadata,
            limit=limit,
            include=["documents", "metadatas"]
        )

        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])
        paired = sorted(
            zip(metadatas, documents),
            key=lambda item: item[0].get("chunk_index", 0)
        )

        return [
            {
                "text": text,
                "metadata": metadata,
            }
            for metadata, text in paired
        ]
