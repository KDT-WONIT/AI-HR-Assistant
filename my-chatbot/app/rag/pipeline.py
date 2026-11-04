import logging
import re
import time

from starlette.concurrency import run_in_threadpool

from app import timing
from app.config import settings
from app.rag.embeddings import EmbeddingService
from app.rag.retrieval import RetrievalHints, focus_grades, pay_amount_question, rank_sources, search_queries
from app.rag.tables import expand_sources, is_table_fragment
from app.rag.vector_store import ChromaVectorStore
from app.schemas import Source

logger = logging.getLogger(__name__)

# 선택된 업무 분야 밖의 문서가 이 값보다 더 가까우면(거리가 작으면) 도구 선택이 빗나간 것으로 보고 전체 문서 검색 결과를 씁니다.
CROSS_DOMAIN_MARGIN = 0.05


def best_distance(groups: list[list[Source]]) -> float | None:
    distances = [source.distance for group in groups for source in group if source.distance is not None]
    return min(distances) if distances else None


def prefer_global(domain: float | None, overall: float | None) -> bool:
    return overall is not None and (domain is None or overall + CROSS_DOMAIN_MARGIN < domain)


class RagService:
    async def search(self, question: str, patterns: list[str], top_k: int | None = None,
                     hints: RetrievalHints | None = None) -> list[Source]:
        count = top_k or settings.rag_top_k
        if pay_amount_question(question):
            count = max(count, 6)  # 금액표는 여러 조각으로 나뉘므로 후보를 조금 더 확보합니다.
        queries = search_queries(question, hints)
        started = time.monotonic()
        if len(queries) == 1:
            vector = await run_in_threadpool(EmbeddingService().embed_query, question)
            embedded = time.monotonic()
            store = ChromaVectorStore()
            def single():
                domain = store.search(vector, patterns, count)
                overall = store.search(vector, None, count) if patterns else domain
                if overall is not domain and prefer_global(best_distance([domain]), best_distance([overall])):
                    logger.info('도구 분야 밖 문서가 더 적합해 전체 문서 검색 결과를 사용합니다(분야 %s → 전체 %s)',
                                best_distance([domain]), best_distance([overall]))
                    return overall
                return domain
            sources = await run_in_threadpool(single)
        else:
            vectors = await run_in_threadpool(EmbeddingService().embed_documents, queries)
            embedded = time.monotonic()
            store = ChromaVectorStore()
            def retrieve():
                groups = [store.search(vector,patterns,min(count*2,20)) for vector in vectors]
                if patterns:
                    overall = [store.search(vector,None,min(count*2,20)) for vector in vectors]
                    if prefer_global(best_distance(groups), best_distance(overall)):
                        logger.info('도구 분야 밖 문서가 더 적합해 전체 문서 검색 결과를 사용합니다(분야 %s → 전체 %s)',
                                    best_distance(groups), best_distance(overall))
                        groups = overall
                return rank_sources(question,groups,count,hints)
            sources = await run_in_threadpool(retrieve)
        searched = time.monotonic()
        restored = await self.restore_tables(sources, hints, question)
        timing.record('임베딩', embedded - started, f'질문 {len(queries)}개')
        timing.record('벡터 검색', searched - embedded)
        timing.record('표 복원', time.monotonic() - searched)
        return restored

    async def restore_tables(self, sources: list[Source], hints: RetrievalHints | None, question: str = '') -> list[Source]:
        """표 조각은 이웃 청크와 이어 붙여 행(등급·금액·구분)으로 복원하고 사용자 직급의 행을 강조합니다."""
        if not any(is_table_fragment(source.text) for source in sources):
            return sources
        # 금액 질문이거나 질문에 직급이 직접 나올 때만 해당 직급의 행으로 좁힙니다(다른 질문의 표를 가리지 않도록).
        explicit = focus_grades(question)
        focus = explicit if explicit and re.search(r'\d직급', question) else (
            focus_grades(question, hints.grade if hints else None) if pay_amount_question(question) else [])
        def restore():
            try:
                return expand_sources(sources, focus, ChromaVectorStore().fetch)
            except Exception:
                logger.warning('표 복원을 건너뛰고 검색된 원본 조각을 사용합니다.', exc_info=True)
                return sources
        return await run_in_threadpool(restore)
