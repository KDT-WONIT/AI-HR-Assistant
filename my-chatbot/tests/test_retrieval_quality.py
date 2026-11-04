import asyncio
import unittest
from unittest.mock import patch, Mock

from app.rag.pipeline import RagService
from app.rag.retrieval import search_queries, rank_sources
from app.schemas import Source


class RetrievalQualityTests(unittest.TestCase):
    def test_procedure_expands_to_regulation_vocabulary(self):
        queries=search_queries('연차휴가는 어떻게 신청하나요?')
        self.assertEqual(len(queries),3)
        self.assertTrue(any('근태계' in item for item in queries))
        self.assertTrue(any('청구' in item for item in queries))
        self.assertEqual(search_queries('학자금 지원 한도?'),['학자금 지원 한도?'])

    def test_common_attendance_procedure_is_ranked_before_carryover(self):
        carry=Source(document='시행세칙.pdf',text='연차휴가는 이월한다.',chunk_id='carry')
        procedure=Source(document='시행세칙.pdf',text='각종 근태계의 제출은 전자결재로 승인받는다.',chunk_id='procedure')
        ranked=rank_sources('연차휴가는 어떻게 신청하나요?',[[carry],[procedure,carry]],5)
        self.assertEqual([s.chunk_id for s in ranked],['procedure','carry'])

    def test_search_batches_expansion_and_keeps_document_filter(self):
        sources=[[Source(document='시행세칙.pdf',text='각종 근태계 전자결재 제출',chunk_id='common')],[],[]]
        with patch('app.rag.pipeline.EmbeddingService') as embedding, patch('app.rag.pipeline.ChromaVectorStore') as store:
            embedding.return_value.embed_documents.return_value=[[1],[2],[3]]
            domain_hits=iter(sources)
            store.return_value.search.side_effect=lambda vector,patterns,count: next(domain_hits) if patterns is not None else []
            result=asyncio.run(RagService().search('연차휴가는 어떻게 신청하나요?',['취업규칙'],5))
            self.assertEqual(result[0].chunk_id,'common')
            self.assertEqual(embedding.return_value.embed_documents.call_count,1)
            domain_calls=[call for call in store.return_value.search.call_args_list if call.args[1] is not None]
            self.assertEqual(len(domain_calls),3)
            for call in domain_calls:
                self.assertEqual(call.args[1],['취업규칙'])

    def test_falls_back_to_all_documents_when_the_routed_domain_has_only_weak_matches(self):
        weak=Source(document='직무권한세칙.pdf',text='위임전결 기준',chunk_id='weak',distance=0.52)
        strong=Source(document='주택융자 운영업무 기준.pdf',text='주택자금 대부 한도액은 7,000만원',chunk_id='strong',distance=0.40)
        with patch('app.rag.pipeline.EmbeddingService') as embedding, patch('app.rag.pipeline.ChromaVectorStore') as store:
            embedding.return_value.embed_query.return_value=[1]
            store.return_value.search.side_effect=lambda vector,patterns,count: [weak] if patterns is not None else [strong]
            result=asyncio.run(RagService().search('주택 구입을 위한 사내 대출이 있나요?',['직무권한'],5))
            self.assertEqual([item.chunk_id for item in result],['strong'])
            # 선택된 분야에서도 충분히 가까우면 분야 안 결과를 그대로 씁니다.
            near=Source(document='직무권한세칙.pdf',text='위임전결',chunk_id='near',distance=0.38)
            store.return_value.search.side_effect=lambda vector,patterns,count: [near] if patterns is not None else [strong]
            result=asyncio.run(RagService().search('위임전결 기준은?',['직무권한'],5))
            self.assertEqual([item.chunk_id for item in result],['near'])
