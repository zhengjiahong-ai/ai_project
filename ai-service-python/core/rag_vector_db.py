import logging
import os
import shutil
import tempfile
import uuid

import chromadb
from chromadb.config import Settings
from grobid_client.grobid_client import GrobidClient
from sentence_transformers import SentenceTransformer

from core.document_parser import parse_tei_xml
from core.pdf_evidence_pages import extract_evidence_pages
from core.smart_chunker import chunk_sections, normalize_section_titles
from rag.store import invalidate_hybrid_cache, normalize_id

_logger = logging.getLogger(__name__)


# 嵌入模型按优先级依次尝试：首选不可用（HF 离线且本地缓存缺失）时逐个回退，
# 避免整个 RAG 降级成 DummyRAG 而全面瘫痪。
# collection 名必须与模型绑定：不同模型的向量维度与语义空间不相容，
# 一旦错配（用 A 模型建的索引去用 B 模型查询）检索结果会完全错乱。
#
# 选型依据（真实 GROBID 论文 28 个 chunk、10 中 + 10 英查询、CPU 实测）：
#   bge-small-en-v1.5  EN@1 7/10  ZH@1 2/10  索引 181ms/条  查询 67ms
#   e5-small           EN@1 7/10  ZH@1 5/10  索引 374ms/条  查询 69ms  <- 首选
#   bge-m3             EN@1 5/10  ZH@1 4/10  索引 3168ms/条 查询 325ms
# 语料是英文论文、提问常用中文，跨语言召回只能靠多语言嵌入（BM25 是词汇匹配，
# 中文查询永远匹不上英文正文）。bge-m3 虽大，在本场景下英文反而退步、中文不及
# e5-small，且索引慢 17 倍（重建全库要半小时），故不入选。
EMBEDDING_MODEL_CANDIDATES = (
    ("intfloat/multilingual-e5-small", "literature_collection_v4_e5_small"),
    ("BAAI/bge-small-en-v1.5", "literature_collection_v3"),
)

EMBEDDING_MODEL_NAME = EMBEDDING_MODEL_CANDIDATES[0][0]

# e5 系列靠对称前缀区分查询与文档，缺失会明显掉点；bge 系列不需要前缀。
_PREFIXED_MODEL_MARKER = "e5"


def _model_prefixes(model_name):
    if _PREFIXED_MODEL_MARKER in str(model_name or "").lower():
        return "query: ", "passage: "
    return "", ""


CHROMA_DB_PATH = os.environ.get(
    "CHROMA_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_literature_db"),
)


class LiteratureRAG:
    # 类级默认值：现有测试用 object.__new__ 绕过 __init__ 再手工注入 embedding_model，
    # 没有这两个属性会在 add_sections_to_db 里抛 AttributeError。
    query_prefix = ""
    passage_prefix = ""
    embedding_model_name = EMBEDDING_MODEL_NAME

    @staticmethod
    def normalize_id(id_str):
        """ 归一化 ID，去除特殊字符，防止编码不一致导致的检索失败 """
        return normalize_id(id_str)

    def __init__(self):

        self.embedding_model, self.embedding_model_name, collection_name = self._load_embedding_model()
        self.query_prefix, self.passage_prefix = _model_prefixes(self.embedding_model_name)

        self.chroma_client = chromadb.PersistentClient(
            path=CHROMA_DB_PATH,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={
                "hnsw:space": "cosine"
            }
        )

    @staticmethod
    def _load_embedding_model():
        """按候选顺序加载第一个可用的嵌入模型。

        模型从 HF Hub 拉取并缓存在 huggingface_cache 数据卷里；网络不可达且缓存缺失时，
        必须能回退到本地已有的模型，否则服务会直接失去 RAG 能力。
        """
        last_error = None
        for model_name, collection_name in EMBEDDING_MODEL_CANDIDATES:
            try:
                model = SentenceTransformer(model_name)
            except Exception as error:
                last_error = error
                _logger.warning("嵌入模型 %s 加载失败，尝试下一个候选: %s", model_name, error)
                continue

            if model_name != EMBEDDING_MODEL_CANDIDATES[0][0]:
                _logger.warning(
                    "首选嵌入模型不可用，已回退到 %s（索引集合 %s）。回退模型的向量空间与首选不同，"
                    "已有索引需重新上传论文才能命中。",
                    model_name,
                    collection_name,
                )
            else:
                _logger.info("嵌入模型就绪: %s -> %s", model_name, collection_name)

            return model, model_name, collection_name

        raise RuntimeError(f"所有嵌入模型候选均加载失败，最后错误: {last_error}")

    def parse_literature(self, file_path):

        input_dir = tempfile.mkdtemp()
        output_dir = tempfile.mkdtemp()

        try:

            shutil.copy(file_path, input_dir)

            grobid = GrobidClient(
                grobid_server="http://grobid:8070",
                queue_size=1
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
        metadata = dict(literature_metadata or {})
        metadata["file_name"] = os.path.basename(file_path)
        # GROBID 的 TEI 章节才是主索引源：它带真实章节标题、公式（Equation: ...）与表格文本，
        # 并且从 coords 推出了 pageIndex/page，引文锚点并不依赖分页文本。
        # 旧实现无条件用 PyPDF2 逐页文本覆盖 TEI，导致索引里 64% 的片段标题退化成 "Page N"，
        # 章节语义与公式全部丢失；同时那句 Front Matter 过滤写在覆盖之后，形同虚设。
        # 现在只在 TEI 没解析出任何正文时才回退到分页文本。
        indexable_sections = normalize_section_titles(sections)
        if not indexable_sections and os.path.isfile(file_path):
            _logger.warning(
                "论文 %s 的 TEI 未解析出正文章节，回退到 PyPDF2 分页文本入库。",
                metadata["file_name"],
            )
            indexable_sections = normalize_section_titles(extract_evidence_pages(file_path))
        chunks = chunk_sections(indexable_sections)
        
        # --- 核心改进：兜底逻辑 ---
        if not chunks:
            _logger.warning("论文 %s 未提取到结构化章节，尝试全文聚合切分。", metadata['file_name'])
            full_text = ""
            for sec in indexable_sections:
                if sec.get("content"):
                    full_text += f"\n{sec['content']}"

            # 章节存在但正文全空时，仍然尝试从 PDF 页面抢救文本
            if not full_text.strip() and os.path.isfile(file_path):
                for sec in extract_evidence_pages(file_path):
                    if sec.get("content"):
                        full_text += f"\n{sec['content']}"
            
            if full_text.strip():
                fallback_sections = [{"section": "Full Text", "content": full_text}]
                chunks = chunk_sections(fallback_sections)
            
            if not chunks:
                _logger.error("论文 %s 彻底未提取到有效文本内容，跳过入库。", metadata['file_name'])
                return 0
        
        # 归一化元数据中的 ID
        if "id" in metadata:
            metadata["id"] = self.normalize_id(metadata["id"])

        # documents 存完整可读文本（论文标题 + 章节 + 正文），供前端引文与 LLM 证据使用；
        # 向量只用“章节标题 + 正文”编码：Paper: {title} 对同一篇论文的所有 chunk 都是常量，
        # 它给向量叠加一个共同分量、稀释正文语义，还占掉 900 字符 chunk 里约 10% 的预算。
        documents = [
            f"Paper: {metadata.get('title','unknown')}\n\nSection: {c['section']}\n\nContent:\n{c['text']}"
            for c in chunks
        ]
        embedding_inputs = [
            f"{self.passage_prefix}Section: {c['section']}\n{c['text']}"
            for c in chunks
        ]

        embeddings = self.embedding_model.encode(
            embedding_inputs,
            normalize_embeddings=True
        ).tolist()

        ids = [str(uuid.uuid4()) for _ in documents]

        metadatas = []
        for i, chunk in enumerate(chunks):
            chunk_metadata = {**metadata, "chunk_index": i}
            optional_metadata = {
                "section_id": chunk.get("sectionId") or chunk.get("section_id"),
                "section_title": chunk.get("sectionTitle") or chunk.get("section"),
                "page_index": chunk.get("pageIndex") if chunk.get("pageIndex") is not None else chunk.get("page_index"),
                "page": chunk.get("page"),
            }
            for key, value in optional_metadata.items():
                if value is not None and value != "":
                    chunk_metadata[key] = value
            metadatas.append(chunk_metadata)

        previous_ids = self.collection.get(where={"id": metadata["id"]}, include=[])["ids"] if metadata.get("id") else []
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )

        if previous_ids:
            self.collection.delete(ids=previous_ids)
        invalidate_hybrid_cache()

        return len(documents)

    def retrieve(self, query, top_k=5, filter_metadata=None):

        query_embedding = self.embedding_model.encode(
            f"{self.query_prefix}{query}",
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
        _logger.info("RAG 检索完成: 查询='%s...', 匹配到 %d 条片段", query[:30], total_found)

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

    def get_db_stats(self):
        return self.collection.count()

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
