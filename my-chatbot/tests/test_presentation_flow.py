import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.agent.followups import contextual_question
from app.integrations.trip_input import normalize_arguments
from app.rag.retrieval import search_queries, rank_sources
from app.schemas import ToolArguments, ToolInput, Source, AnswerContext


class PresentationContextTests(unittest.TestCase):
    def test_question_intent_is_preserved_and_old_trip_facts_remain_available(self):
        history=[{'role':'user','content':'2026년 10월 19일부터 부산 20박 21일 출장. 왕복 600km, KTX 10만원.'}]
        history += [{'role':'user','content':f'다른 질문 {n}'} for n in range(7)]
        question='아까 말한 출장비를 계산해줘.'
        resolved=contextual_question(question,history)
        self.assertTrue(resolved.startswith(question))
        self.assertIn('왕복 600km',resolved)
        self.assertNotIn('다른 질문',resolved)

    def test_birth_followup_does_not_change_days_question_into_eligibility(self):
        question='그럼 경조사 휴가는 며칠 쓸 수 있어?'
        resolved=contextual_question(question,[{'role':'user','content':'배우자가 둘째 아이 한 명을 출산할 예정이야.'}])
        self.assertTrue(resolved.startswith(question))
        self.assertIn('둘째 아이 한 명',resolved)

    def test_standalone_new_topic_and_assistant_claims_do_not_leak(self):
        history=[{'role':'user','content':'배우자 출산 예정이야.'}, {'role':'assistant','content':'거짓 지급액 100만원'}]
        self.assertEqual(contextual_question('내 잔여 연차는 며칠이야?',history),'내 잔여 연차는 며칠이야?')
        self.assertNotIn('100만원',contextual_question('이 경우 지원금은?',history))
        self.assertEqual(contextual_question('그 휴가는 어떻게 신청해?',[]),'그 휴가는 어떻게 신청해?')

    def test_explicit_trip_facts_override_conflicting_model_arguments(self):
        args=ToolArguments(trip={'trip_type':'domestic','destination_city':'부산','distance_km':0,'same_city':True,'transport_mode':'private_car'})
        actual=normalize_arguments('아까 출장비 계산해줘','본사와 다른 시군이며 왕복 600km야. KTX 20박 21일, 식비 지급 대상은 21일',args)
        self.assertEqual(actual.trip['transport_mode'],'public_transport')
        self.assertEqual(actual.trip['distance_km'],600)
        self.assertFalse(actual.trip['same_city'])
        self.assertEqual(actual.trip['domestic_region_type'],'metropolitan_city')
        self.assertEqual(actual.trip['lodging_nights'],20)
        self.assertEqual(actual.trip['meal_days'],21)

    def test_payout_question_does_not_recalculate_or_guess_leave_days(self):
        args=ToolArguments(requested_days=21,trip={'start_date':'2024-01-01'})
        actual=normalize_arguments('그 출장비는 언제 지급돼?','20박 21일 출장',args)
        self.assertIsNone(actual.trip)
        self.assertIsNone(actual.requested_days)

    def test_birth_leave_does_not_query_annual_ledger(self):
        from app.tools.execution import business_data
        with patch('app.tools.execution.connection_scope') as connection:
            data, missing=business_data('work_labor',ToolInput(question='배우자 출산 경조휴가는 며칠?',employee_id='A',conversation_id=uuid4()))
        self.assertNotIn('leave_balance',data)
        connection.assert_not_called()

    def test_childbirth_benefit_search_prioritizes_welfare_over_gift_limits(self):
        question='배우자의 둘째 출산 경조사 지원금은 얼마야?'
        self.assertTrue(any('출산축하금' in query for query in search_queries(question)))
        gift=Source(document='임직원 행동강령.pdf',text='경조사비 5만원',chunk_id='gift')
        benefit=Source(document='복리후생규정.pdf',text='제12조(출산경조금) 둘째 자녀부터 지급한다.',chunk_id='benefit')
        self.assertEqual(rank_sources(question,[[gift,benefit]],2)[0].chunk_id,'benefit')

    def test_singleton_second_child_uses_basic_days_from_retrieved_table(self):
        from app.agent.leave_answers import spouse_leave_answer
        context=AnswerContext(employee_id='A',question='경조사 휴가는 며칠?\n배우자가 둘째 아이 한 명을 출산할 예정',sources=[
            Source(document='규정.pdf',page=22,text='배우자 출산전후휴가 (한번에 둘 이상) · 휴가일 20일 (25일)')])
        answer=spouse_leave_answer(context)
        self.assertTrue(answer.startswith('말씀하신 배우자 출산 경조휴가는 20일입니다.'))
        context.sources[0].text='배우자 출산전후휴가 · 휴가일 17일 (23일)'
        self.assertIn('17일입니다',spouse_leave_answer(context))  # 결과를 상수로 고정하지 않음

    def test_twins_use_conditional_days_and_missing_table_does_not_invent(self):
        from app.agent.leave_answers import spouse_leave_answer
        context=AnswerContext(employee_id='A',question='배우자가 쌍둥이 출산 시 휴가 며칠?',sources=[
            Source(document='규정.pdf',text='배우자 출산전후휴가 · 휴가일 20일 (25일)')])
        self.assertIn('25일입니다',spouse_leave_answer(context))
        context.sources=[]
        self.assertIsNone(spouse_leave_answer(context))

    def test_application_includes_evidence_attachment_and_prior_permission(self):
        from app.agent.leave_answers import spouse_leave_answer
        context=AnswerContext(employee_id='A',question='배우자 출산휴가는 어떻게 신청해?',sources=[
            Source(document='시행세칙.pdf',page=3,text='각종 근태계의 제출은 전산시스템 양식에 따라 전자결재로 한다.\n제21조에 따른 휴가 요청시 사실을 증명할 서류를 첨부한다.'),
            Source(document='취업규칙.pdf',page=10,text='특별유급휴가를 얻으려는 직원은 사전에 소속 부서장의 허가를 받아야 한다.')])
        answer=spouse_leave_answer(context)
        self.assertIn('증명하는 서류',answer)
        self.assertIn('전자결재',answer)
        self.assertIn('소속 부서장의 허가',answer)

    def test_payout_intent_ignores_earlier_calculation_request(self):
        from app.tools.execution import business_data
        request=ToolInput(employee_id='A',conversation_id=uuid4(),question='그 출장비는 언제 지급돼?\n\n[생략된 대상 이해용]\n앞서 예상액 계산을 요청함')
        with patch('app.tools.execution.travel_expense') as calculate:
            data,_=business_data('travel_expenses',request)
        calculate.assert_not_called()
        self.assertNotIn('travel_expense',data)

    def test_report_deadline_is_not_a_bank_payment_date(self):
        from app.agent.travel_answers import travel_payment_answer
        context=AnswerContext(employee_id='A',question='그 출장비는 언제 지급돼?',sources=[
            Source(document='여비규정.pdf',page=5,text='국내출장자는 근무지로 복귀한 경우 7일 이내에 교통수단 이용 증명서 및 숙박비 증명서를 첨부하여 복명서를 제출한다.')])
        answer=travel_payment_answer(context)
        self.assertTrue(answer.startswith('실제 출장비 입금일은 검색된 규정에서 확인할 수 없습니다.'))
        self.assertIn('복명서 제출 기한',answer)
        context.sources.append(Source(document='실제지급일.pdf',text='지급일은 매월 25일입니다.'))
        self.assertIsNone(travel_payment_answer(context))

    def test_leave_chain_is_not_treated_as_approved_by_general_entitlement(self):
        from app.agent.leave_answers import leave_chain_answer
        context=AnswerContext(employee_id='A',question='경조휴가에 이어서 연차를 쓸 수 있어?',sources=[
            Source(document='취업규칙.pdf',text='연차유급휴가는 직원의 자유의사에 따라 적절히 사용할 수 있다.')])
        answer=leave_chain_answer(context)
        self.assertIn('승인되었다고 확정할 수는 없습니다',answer)
        self.assertEqual(context.answer_coverage,'partial')


if __name__=='__main__': unittest.main()
