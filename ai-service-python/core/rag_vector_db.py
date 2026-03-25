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


EMBEDDING_MODEL_NAME = "BAAI/bge-large-en-v1.5"

CHROMA_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "chroma_literature_db"
)


class LiteratureRAG:

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
            name="literature_collection",
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

        sections = self.parse_literature(file_path)

        metadata = literature_metadata or {}
        metadata["file_name"] = os.path.basename(file_path)

        chunks = chunk_sections(sections)

        texts = [
            f"""
Paper: {metadata.get('title','unknown')}

Section: {c['section']}

Content:
{c['text']}
"""
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

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata,
            include=["documents", "distances", "metadatas"]
        )

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