from rank_bm25 import BM25Okapi


class HybridRetriever:

    def __init__(self, rag):

        self.rag = rag

        data = rag.collection.get()

        self.docs = data["documents"]

        tokenized = [d.split() for d in self.docs]

        self.bm25 = BM25Okapi(tokenized)

    def retrieve(self, query, top_k=5):

        vector_results = self.rag.retrieve(query, top_k)

        scores = self.bm25.get_scores(query.split())

        ranked = sorted(
            zip(self.docs, scores),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]

        bm25_results = [
            {"text": r[0], "score": r[1]}
            for r in ranked
        ]

        return {
            "vector": vector_results,
            "bm25": bm25_results
        }