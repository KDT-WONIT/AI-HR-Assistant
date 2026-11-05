import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import AsyncMock,Mock,patch
from uuid import uuid4

from app.config import settings
from app.agent.business_answers import structured_answer
from app.integrations.employee_tools import inquiry_history,travel_expense,travel_policy_matches
from app.repositories.memory import MemoryConversationRepository
from app.repositories.sqlite import SQLiteConversationRepository
from app.schemas import ToolInput,ToolArguments,ToolResult,AnswerContext,UserProfile,Message
from app.tools.execution import business_data,execute_domain


class ReceivedToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner=asyncio.Runner()

    @classmethod
    def tearDownClass(cls):
        cls.runner.close()

    def setUp(self):
        self.request=ToolInput(employee_id='A',conversation_id=uuid4(),question='출장비 계산',
                               user_profile=UserProfile(employee_id='A',name='사원 A',grade='3직급'))
        self.trip=dict(trip_type='domestic',start_date='2026-11-05',end_date='2026-11-06',destination_city='부산',
                       distance_km=600,same_city=False,domestic_region_type='metropolitan_city',
                       transport_cost_krw=100000,lodging_cost_per_night=80000)

    def calculate(self,trip=None,request=None):
        with patch('app.integrations.employee_tools.travel_policy_matches',return_value=True):
            return travel_expense(request or self.request,ToolArguments(trip=trip or self.trip))

    def answer(self,result):
        context=AnswerContext(employee_id='A',question='출장비',tool_results=[ToolResult(tool_id='travel_expenses',status='ok',message='',data={'travel_expense':result})])
        return context,structured_answer(context)

    def test_domestic_amount_uses_db_grade_and_verified_policy(self):
        result=self.calculate()
        self.assertEqual(result['status'],'success')
        self.assertEqual(result['data']['travel_grade'],'grade_3')
        self.assertEqual(result['data']['estimated_total_krw'],'290000.00')
        context,text=self.answer(result)
        self.assertEqual(context.answer_coverage,'direct')
        self.assertIn('290,000원',text)
        self.assertIn('여비규정',text)
        self.assertIn('정산 확정액이 아닙니다',text)

    def test_missing_transport_does_not_become_zero_or_a_total(self):
        trip={k:v for k,v in self.trip.items() if k!='transport_cost_krw'}
        result=self.calculate(trip)
        self.assertEqual(result['status'],'partial')
        self.assertIsNone(result['data']['estimated_total_krw'])
        context,text=self.answer(result)
        self.assertEqual(context.answer_coverage,'partial')
        self.assertIn('입력이 더 필요합니다: 교통비 예정 금액',text)

    def test_unknown_grade_falls_back_to_assumed_grade(self):
        profile=self.request.user_profile.model_copy(update={'grade':'미분류','job_title':'부서장'})
        result=self.calculate(request=self.request.model_copy(update={'user_profile':profile}))
        self.assertEqual(result['status'],'success')
        self.assertTrue(any('가정' in note for note in result['assumptions']))

    def test_policy_mismatch_blocks_fixed_rate_calculation(self):
        with patch('app.integrations.employee_tools.travel_policy_matches',return_value=False):
            result=travel_expense(self.request,ToolArguments(trip=self.trip))
        self.assertEqual(result['status'],'needs_review')
        self.assertNotIn('data',result)

    def test_grade_spoof_and_invalid_trip_are_rejected(self):
        for fields in [{'travel_grade':'executive'},{'employee_id':'B'},{'end_date':'2026-10-01'},{'same_city':'false'}]:
            with self.subTest(fields=fields):
                self.assertEqual(self.calculate(self.trip|fields)['status'],'error')

    def test_near_distance_does_not_double_count_transport(self):
        result=self.calculate(self.trip|dict(end_date='2026-11-05',distance_km=8,same_city=True,transport_cost_krw=100000))
        self.assertEqual(result['data']['estimated_total_krw'],'20000.00')

    def test_exception_and_overseas_missing_days_request_review_or_input(self):
        result=self.calculate(self.trip|{'special_conditions':['기관 부담']})
        self.assertEqual(result['status'],'needs_review')
        context,text=self.answer(result)
        self.assertEqual(context.answer_coverage,'missing')
        self.assertIn('담당자 확인',text)
        result=self.calculate(self.trip|{'trip_type':'overseas','destination_country':'일본'})
        self.assertEqual(result['status'],'error')

    def test_travel_tool_without_inputs_does_not_search_unrelated_rules(self):
        with patch('app.tools.execution.RagService.search',AsyncMock()) as rag:
            result=self.runner.run(execute_domain('travel_expenses',['여비'],self.request))
        self.assertEqual(result.status,'needs_input')
        self.assertIn('4가지 정보',result.message)  # 출장비 계산기가 빠진 항목을 되묻습니다
        rag.assert_not_awaited()

    def populate(self,repository,employee,question,answer):
        conversation=repository.create(employee)
        now=datetime.now(timezone.utc)
        repository.append_turn(conversation.id,[Message(id=uuid4(),role='user',content=question,created_at=now),
            Message(id=uuid4(),role='assistant',content=answer,created_at=now,tools_used=['work_labor'])],
            AnswerContext(employee_id=employee,question=question),None)

    def test_history_joins_pairs_across_own_sessions_and_excludes_other_employees(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('app.integrations.sqlite.settings',replace(settings,sqlite_path=Path(temp)/'history.sqlite3')):
                repository=SQLiteConversationRepository()
                self.populate(repository,'A','연차 신청','전자결재로 제출')
                self.populate(repository,'A','여비 문의','출장 답변')
                self.populate(repository,'B','연차 신청','다른 사람 비공개 답변')
                for keyword in ['연차','전자결재','work_labor',"' OR 1=1 --"]:
                    results=repository.search_inquiries('A',keyword,100)
                    self.assertTrue(all(item['employee_id']=='A' for item in results))
                self.assertEqual(repository.search_inquiries('A','연차',100)[0]['answer'],'전자결재로 제출')
                self.assertEqual(len(repository.search_inquiries('A','',100)),2)
                self.assertEqual(repository.search_inquiries('A',"' OR 1=1 --",100),[])

    def test_received_history_ranking_and_empty_result_rendering(self):
        repository=MemoryConversationRepository()
        self.populate(repository,'A','연차 이월 문의','과거 규정 답변')
        self.populate(repository,'B','연차 이월 문의','노출하면 안 되는 답변')
        with patch('app.integrations.employee_tools.create_repository',return_value=repository):
            result=inquiry_history(self.request,ToolArguments(history_query='연차 이월'))
            self.assertEqual(result['data']['count'],1)
            self.assertNotIn('노출하면 안 되는',str(result))
            context=AnswerContext(employee_id='A',question='이전 문의',tool_results=[ToolResult(tool_id='organization_management',status='ok',message='',data={'inquiry_history':result})])
            self.assertIn('현재 규정과 다시 대조',structured_answer(context))
            self.assertEqual(context.answer_coverage,'direct')
            result=inquiry_history(self.request,ToolArguments(history_query='천체물리학'))
            self.assertEqual(result['data']['count'],0)

    def test_history_intent_bypasses_rag_even_if_domain_selection_is_broad(self):
        self.request.question='이전 문의 이력 보여줘'
        with patch('app.integrations.employee_tools.create_repository',return_value=MemoryConversationRepository()),patch('app.tools.execution.RagService.search',AsyncMock()) as rag:
            result=self.runner.run(execute_domain('hr_employment',['인사'],self.request))
        self.assertIn('inquiry_history',result.data)
        rag.assert_not_awaited()

    def test_router_history_query_on_ordinary_question_does_not_trigger_history(self):
        self.request.question='자기계발 교육비 지원 기준을 알려주세요'
        self.request.arguments={'history_query':'자기계발 교육비'}
        with patch('app.integrations.employee_tools.create_repository',return_value=MemoryConversationRepository()),patch('app.tools.execution.RagService.search',AsyncMock(return_value=[])) as rag:
            result=self.runner.run(execute_domain('pay_benefits',['복리후생'],self.request))
        self.assertNotIn('inquiry_history',result.data)
        rag.assert_awaited()

    def test_policy_hash_validation_requires_all_evidence_chunks(self):
        travel_policy_matches.cache_clear()
        collection=Mock()
        collection.get.return_value={'ids':[],'metadatas':[]}
        with patch('app.integrations.employee_tools.get_collection',return_value=collection):
            self.assertFalse(travel_policy_matches('test','collection'))
        travel_policy_matches.cache_clear()
