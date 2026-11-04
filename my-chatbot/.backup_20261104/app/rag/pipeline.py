from app.schemas import Source
from starlette.concurrency import run_in_threadpool
from app.config import settings
from app.rag.embeddings import EmbeddingService
from app.rag.vector_store import ChromaVectorStore
from app.rag.retrieval import search_queries, rank_sources


class RagService:
    async def search(self, question: str, patterns: list[str], top_k: int | None = None) -> list[Source]:
        count = top_k or settings.rag_top_k
        queries = search_queries(question)
        if len(queries) == 1:
            vector = await run_in_threadpool(EmbeddingService().embed_query, question)
            return await run_in_threadpool(ChromaVectorStore().search, vector, patterns, count)
        vectors = await run_in_threadpool(EmbeddingService().embed_documents, queries)
        store = ChromaVectorStore()
        def retrieve():
            groups = [store.search(vector,patterns,min(count*2,20)) for vector in vectors]
            return rank_sources(question,groups,count)
        return await run_in_threadpool(retrieve)
