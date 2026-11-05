import sqlite3
import unittest
from uuid import uuid4

from app.agent.business_answers import structured_answer
from app.integrations import travel_calc
from app.integrations.leave_balance import balance_only_question, load_balance
from app.schemas import AnswerContext, ToolResult


class TravelCalculatorTests(unittest.TestCase):
    def test_extracts_four_inputs_from_natural_sentences(self):
        self.assertEqual(travel_calc.extract_inputs('3일 출장 2박 교통비 10만원 1박 숙박비 8만원'),
                         dict(days=3, nights=2, transport_cost=100000.0, lodging_per_night=80000.0))
        self.assertEqual(travel_calc.extract_inputs('2박 3일 교통비 15만원 숙박비 1박 9만 5천원'),
                         dict(days=3, nights=2, transport_cost=150000.0, lodging_per_night=95000.0))
        self.assertEqual(travel_calc.extract_inputs('1박 8만원 교통비 120,000원 2박3일')['lodging_per_night'], 80000.0)

    def test_missing_items_are_requested_again(self):
        self.assertEqual(travel_calc.missing_items({}), ['days', 'nights', 'transport_cost', 'lodging_per_night'])
        self.assertEqual(travel_calc.missing_items({'days': 3, 'nights': 2, 'transport_cost': 1}), ['lodging_per_night'])
        self.assertEqual(travel_calc.missing_items({'days': 1, 'nights': 0, 'transport_cost': 1}), [])  # 숙박 0박이면 숙박비 불필요
        message = travel_calc.request_message({'days': 3})
        self.assertIn('3일', message)
        self.assertIn('(입력 필요)', message)
        self.assertTrue(travel_calc.pending(message))

    def test_previous_answers_are_remembered(self):
        merged = travel_calc.merge_inputs('교통비 10만원 숙박비 8만원', ['3일 2박 출장 계산해줘'])
        self.assertEqual(travel_calc.missing_items(merged), [])
        self.assertEqual((merged['days'], merged['nights']), (3, 2))

    def test_calculation_and_validation(self):
        result = travel_calc.calculate(dict(days=3, nights=2, transport_cost=100000, lodging_per_night=80000), 'grade_2')
        self.assertEqual((result['allowance'], result['meals'], result['lodging'], result['total']), (75000, 90000, 160000, 425000))
        self.assertTrue(result['lodging_note'])  # 70,000원 초과는 지역 상한 확인 안내
        executive = travel_calc.calculate(dict(days=3, nights=2, transport_cost=0, lodging_per_night=150000), 'executive')
        self.assertEqual(executive['total'], 90000 + 180000 + 300000)
        self.assertEqual(executive['lodging_note'], '')
        same_day = travel_calc.calculate(dict(days=1, nights=0, transport_cost=10000, lodging_per_night=0), 'grade_3')
        self.assertEqual(same_day['meals'], 20000)
        self.assertIn('하루 적어야', travel_calc.validate(dict(days=2, nights=2)))
        self.assertEqual(travel_calc.validate(dict(days=3, nights=2)), '')

    def test_triggers(self):
        self.assertTrue(travel_calc.should_run('출장비 계산해줘', [], ''))
        self.assertFalse(travel_calc.should_run('해외 출장비 계산해줘', [], ''))
        self.assertFalse(travel_calc.should_run('3일 2박이야', [], ''))  # 되묻기 전에는 일반 질문
        self.assertTrue(travel_calc.should_run('3일 2박이야', [], travel_calc.request_message({})))

    def test_answer_shows_calculation(self):
        data = travel_calc.calculate(dict(days=3, nights=2, transport_cost=100000, lodging_per_night=60000), 'grade_2')
        context = AnswerContext(question='출장비 계산', employee_id='A', tool_results=[
            ToolResult(tool_id='travel_expenses', status='ok', message='', data={'travel_calc': data})])
        answer = structured_answer(context)
        self.assertIn('예상 출장비는 **385,000원**', answer)
        self.assertIn('25,000원 × 3일 = 75,000원', answer)
        self.assertIn('**{계산 내역}**', answer)


class LeaveBalanceTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE leave_balances(employee_id TEXT, balance_year INT, granted_days REAL, used_days REAL, updated_at TEXT);
            CREATE TABLE leave_balance_details(employee_id TEXT, balance_year INT, base_days REAL, carryover_days REAL, adjusted_days REAL);
            CREATE TABLE leave_transactions(transaction_id TEXT, employee_id TEXT, leave_type TEXT, deducts_annual_leave INT,
                start_date TEXT, end_date TEXT, days REAL, status TEXT, requested_at TEXT);
            INSERT INTO leave_balances VALUES('W1',2026,17.5,2,'2026-11-03 18:00:00');
            INSERT INTO leave_balance_details VALUES('W1',2026,16,2,-0.5);
            INSERT INTO leave_transactions VALUES('T1','W1','연차',1,'2026-01-08','2026-01-08',1,'USED',NULL);
            INSERT INTO leave_transactions VALUES('T2','W1','반차',1,'2026-07-16','2026-07-16',1,'USED',NULL);
            INSERT INTO leave_transactions VALUES('T3','W1','연차',1,'2026-11-25','2026-11-25',1,'APPROVED',NULL);
            INSERT INTO leave_transactions VALUES('T4','W1','연차',1,'2026-12-13','2026-12-13',0.5,'PENDING',NULL);
            INSERT INTO leave_transactions VALUES('T5','W1','경조휴가',0,'2026-03-03','2026-03-03',3,'USED',NULL);
        """)

    def test_balance_breakdown(self):
        item = load_balance(self.connection, 'W1', 2026)
        self.assertEqual((item['base_days'], item['carryover_days'], item['adjusted_days']), (16, 2, -0.5))
        self.assertEqual((item['granted_days'], item['used_days'], item['remaining_days']), (17.5, 2, 15.5))
        self.assertEqual((item['scheduled_days'], item['pending_days'], item['remaining_after_scheduled_days']), (1, 0.5, 14))
        self.assertEqual(len(item['recent_used']), 2)  # 경조휴가는 연차 차감이 아니라 제외
        self.assertIsNone(load_balance(self.connection, 'W9', 2026))

    def test_balance_answer_is_calculated_from_db(self):
        item = load_balance(self.connection, 'W1', 2026)
        context = AnswerContext(question='내 남은 연차 알려줘', employee_id='W1', tool_results=[
            ToolResult(tool_id='work_labor', status='ok', message='', data={'leave_balance': item})])
        answer = structured_answer(context)
        self.assertIn('잔여 연차는 **15.5일**', answer)
        self.assertIn('이월: +2일', answer)
        self.assertIn('조정(정산): -0.5일', answer)
        self.assertIn('11/25 연차 1일 (승인)', answer)
        self.assertIn('잔여 연차는 14일이 됩니다', answer)  # 예정 반영 후 잔여

    def test_policy_questions_are_not_taken_over(self):
        self.assertTrue(balance_only_question('내 남은 연차 며칠이야?'))
        self.assertFalse(balance_only_question('연차 신청 방법 알려줘'))


if __name__ == '__main__':
    unittest.main()


class TravelEstimateAnswerTests(unittest.TestCase):
    def build(self):
        from app.integrations.employee_tools import calculate_travel_expense, EmployeeContext
        trip = dict(trip_type='domestic', destination_city='부산', start_date='2026-11-10', end_date='2026-11-12',
                    transport_mode='public_transport', transport_cost_krw=120000, distance_km=800, same_city=False,
                    domestic_region_type='metropolitan_city', lodging_nights=2, meal_days=3, lodging_cost_per_night=95000)
        return calculate_travel_expense(trip, context=EmployeeContext('WON0002', {'travel_grade': 'grade_2'}, None))

    def test_form_result_shows_process_total_and_regulation(self):
        from types import SimpleNamespace
        from app.agent.travel_estimate_answers import travel_estimate_answer
        calc = self.build()
        context = SimpleNamespace(tool_results=[SimpleNamespace(data={'travel_expense': calc})], answer_coverage=None)
        fetch = lambda ids: {i: ('제15조 일비는 출장 일수에 따라 정액으로 지급한다. 추가 문구입니다.', {}) for i in ids}
        answer = travel_estimate_answer(context, fetch)
        self.assertIn('**465,000원**', answer)
        self.assertIn('일비: 25,000원 × 3일 = 75,000원', answer)
        self.assertIn('식비: 30,000원 × 3일 = 90,000원', answer)
        self.assertIn('상한을 넘어 상한 적용', answer)
        self.assertIn('**{관련 규정}**', answer)
        self.assertIn('**{참고 문서}**', answer)
        self.assertEqual(context.answer_coverage, 'direct')

    def test_regulation_failure_keeps_calculation(self):
        from types import SimpleNamespace
        from app.agent.travel_estimate_answers import travel_estimate_answer
        context = SimpleNamespace(tool_results=[SimpleNamespace(data={'travel_expense': self.build()})], answer_coverage=None)
        def broken(ids):
            raise RuntimeError('down')
        answer = travel_estimate_answer(context, broken)
        self.assertIn('465,000원', answer)
        self.assertNotIn('{관련 규정}', answer)


class TravelReviewAnswerTests(unittest.TestCase):
    def test_review_gives_reason_inputs_and_next_steps(self):
        from types import SimpleNamespace
        from app.agent.travel_estimate_answers import travel_estimate_answer
        review = {'status': 'needs_review', 'message': '숙박·복수일·동일 시군 50km 이상·렌터카·식사 제공 근거리 출장은 지급 방식 확인이 필요합니다.',
                  'input': {'trip_type': 'domestic', 'destination_city': '서울', 'start_date': '2026-11-10', 'end_date': '2026-11-11',
                            'distance_km': 20, 'same_city': True, 'lodging_nights': 1, 'transport_mode': 'public_transport'}}
        context = SimpleNamespace(tool_results=[SimpleNamespace(data={'travel_expense': review})], answer_coverage=None)
        answer = travel_estimate_answer(context, lambda ids: {})
        self.assertIn('자동으로 금액을 확정할 수 없어', answer)
        self.assertIn('동일 시·군', answer)
        self.assertIn('숙박 없는 당일 출장', answer)
        self.assertEqual(context.answer_coverage, 'missing')


class TravelGradeResolutionTests(unittest.TestCase):
    def test_unmapped_grades_get_a_grade(self):
        from types import SimpleNamespace
        from app.integrations.employee_tools import resolve_travel_grade
        mapping = {'3직급': 'grade_3', '4직급': 'grade_4_plus'}
        self.assertEqual(resolve_travel_grade(SimpleNamespace(grade='3직급', job_title=None), mapping)[0], 'grade_3')
        self.assertEqual(resolve_travel_grade(SimpleNamespace(grade='4직급(가)', job_title=None), mapping)[0], 'grade_4_plus')
        self.assertEqual(resolve_travel_grade(SimpleNamespace(grade=None, job_title='대리'), mapping)[0], 'grade_3')
        grade, note = resolve_travel_grade(SimpleNamespace(grade=None, job_title=None), {})
        self.assertEqual(grade, 'grade_3')
        self.assertIn('가정', note)
