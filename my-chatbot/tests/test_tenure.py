import unittest
from datetime import date
from uuid import uuid4

from app.agent.business_answers import structured_answer
from app.agent.tenure import tenure_info, tenure_question
from app.schemas import AnswerContext, ToolInput, ToolResult
from app.tools.execution import tenure_data


class TenureTests(unittest.TestCase):
    def test_detects_tenure_questions(self):
        for text in ('내가 입사 몇 년차야', '나 몇년차야?', '입사한 지 얼마나 됐어', '근속 기간 알려줘', '회사 다닌 지 몇 년 됐어'):
            self.assertTrue(tenure_question(text), text)

    def test_ignores_other_questions(self):
        for text in ('연차 몇 일 남았어', '근속 2년마다 가산되는 연차 규정', '입사일 알려줘', '출장비 얼마야'):
            self.assertFalse(tenure_question(text), text)

    def test_tenure_info(self):
        info = tenure_info(date(2023, 3, 15), date(2026, 11, 6))
        self.assertEqual((info['years'], info['months'], info['year_rank']), (3, 7, 4))
        self.assertIsNone(tenure_info(date(2027, 1, 1), date(2026, 11, 6)))

    def test_answer_uses_hire_date(self):
        info = tenure_info(date(2023, 3, 15), date(2026, 11, 6)) | {'name': '홍길동', 'is_self': True}
        context = AnswerContext(question='입사 몇 년차야', employee_id='E1',
                                tool_results=[ToolResult(tool_id='hr_employment', status='ok', message='', data={'tenure': info})])
        answer = structured_answer(context)
        self.assertIn('4년차', answer)
        self.assertIn('3년 7개월', answer)
        self.assertEqual(context.answer_coverage, 'direct')

    def test_missing_hire_date_asks_hr(self):
        data, missing = tenure_data(ToolInput(question='입사 몇 년차야', employee_id='E1', conversation_id=uuid4()),
                                    '입사 몇 년차야', tenure_info)
        self.assertEqual(data, {})
        self.assertIn('입사일', missing)


if __name__ == '__main__':
    unittest.main()
