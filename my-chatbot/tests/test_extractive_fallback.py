import asyncio
import json
import unittest
from unittest.mock import AsyncMock

from app.integrations.ollama import OllamaClient
from app.schemas import AnswerContext, Source


class ExtractiveFallbackTests(unittest.TestCase):
    def context(self, question, text):
        return AnswerContext(question=question, employee_id='A',
                             sources=[Source(document='복리후생규정.pdf', page=3, text=text)])

    def test_rejected_model_points_fall_back_to_matching_source_sentences(self):
        context = self.context('자기계발 교육비 지원 기준을 알려주세요', '교육비는 연 100만원 한도로 지원한다. 신청은 소속 부서장의 승인을 받아야 한다. 휴게실은 3층에 있다.')
        client = OllamaClient()
        client._chat = AsyncMock(return_value=json.dumps({'coverage': 'direct', 'summary': '500만원 지원됩니다.', 'points': [
            {'text': '500만원 지원됩니다.', 'source_id': 'S1', 'evidence_id': 'E1'}]}))
        answer = asyncio.run(client.generate_answer(context))
        self.assertNotIn('확실하게 정리하기 어렵', answer)
        self.assertNotIn('500만원', answer)
        self.assertIn('교육비는 연 100만원 한도로 지원한다.', answer)
        self.assertNotIn('휴게실', answer)  # 질문과 겹치지 않는 문장은 섞지 않습니다.
        self.assertEqual(context.answer_coverage, 'partial')

    def test_unrelated_sources_still_report_the_limit(self):
        context = self.context('주차 등록은 어떻게 하나요', '교육비는 연 100만원 한도로 지원한다.')
        client = OllamaClient()
        client._chat = AsyncMock(return_value='{"summary":"잘린')
        answer = asyncio.run(client.generate_answer(context))
        self.assertIn('확실하게 정리하기 어렵습니다', answer)


if __name__ == '__main__':
    unittest.main()
