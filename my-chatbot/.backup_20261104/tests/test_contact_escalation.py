import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.agent.escalation import ContactRecommender
from app.agent.service import ChatService
from app.config import settings
from app.integrations.n8n import DeliveryResult
from app.repositories.memory import MemoryConversationRepository
from app.repositories.sqlite import SQLiteConversationRepository
from app.schemas import (ContactEscalation, DepartmentProfile, UserProfile, ToolDefinition, ToolDecision,
                         ToolResult, ChatRequest, Source)


class FakeDirectory:
    def departments(self):
        return [DepartmentProfile(dept_id='HR',dept_name='인사부',dept_function='인사 운영, 채용'),
                DepartmentProfile(dept_id='PAY',dept_name='급여부',dept_function='급여, 수당, 여비, 학자금'),
                DepartmentProfile(dept_id='BUY',dept_name='공정계약실',dept_function='입찰, 구매, 계약, 공정거래')]

    def contact_candidates(self, ids):
        output=[]
        departments = {item.dept_id:item.dept_name for item in self.departments()}
        for employee,dept,role in [('A','PAY','MANAGER'),('B','PAY','PROCESSOR'),('C','PAY','PROCESSOR'),('D','HR','PROCESSOR'),
                                   ('E','BUY','PROCESSOR'),('F','BUY','PROCESSOR')]:
            if dept not in ids: continue
            profile=UserProfile(employee_id=employee,name='직원'+employee,department=departments[dept],
                                dept_id=dept,work_email=employee.lower()+'@example.com',extension_number='2101',
                                image_url=f'/api/users/{employee}/photo',roles=['실무담당자' if role=='PROCESSOR' else '부서장'])
            output.append({'profile':profile,'role_details':[{'role_category':role,'description':'가상 업무 역할'}]})
        return output


class ContactMatchingTests(unittest.TestCase):
    def setUp(self):
        self.recommender=ContactRecommender(FakeDirectory())

    def test_salary_question_finds_payroll_not_the_questioner_or_manager_first(self):
        result=self.recommender.recommend('나 연봉 언제 오르지','B')
        self.assertEqual(result.status,'recommended')
        self.assertEqual(result.contacts[0].employee.employee_id,'C')
        self.assertTrue(all(item.employee.department=='급여부' for item in result.contacts))
        self.assertTrue(all(item.employee.employee_id!='B' for item in result.contacts))
        self.assertIn('연봉',result.contacts[0].matched_terms)
        self.assertIn('급여',result.contacts[0].reason)
        self.assertTrue(result.contacts[0].employee.image_url)
        self.assertTrue(result.contacts[0].employee.work_email)

    def test_limit_is_configurable(self):
        with patch('app.agent.escalation.settings',replace(settings,contact_recommendation_limit=1)):
            self.assertEqual(len(self.recommender.recommend('학자금 문의','Q').contacts),1)

    def test_unrelated_topic_does_not_assign_a_random_person(self):
        result=self.recommender.recommend('화성 토양의 결정 구조는?','Q')
        self.assertEqual(result.status,'not_found')
        self.assertEqual(result.contacts,[])

    def test_followup_uses_latest_relevant_user_question(self):
        result=self.recommender.recommend('그럼 어디에 문의해?', 'Q',[
            {'role':'user','content':'연차 신청 방법'}, {'role':'assistant','content':'인사부 답변'},
            {'role':'user','content':'연봉 인상일은?'},
        ])
        self.assertEqual(result.contacts[0].employee.department,'급여부')

    def test_unrelated_new_question_does_not_reuse_previous_salary_topic(self):
        result=self.recommender.recommend('화성 토양의 결정 구조는?','Q',[
            {'role':'user','content':'연봉 인상일은?'},
        ])
        self.assertEqual(result.status,'not_found')
        self.assertEqual(result.contacts,[])

    def test_current_question_takes_priority_over_history(self):
        result=self.recommender.recommend('연차 담당자','Q',[{'role':'user','content':'연봉 인상일?'}])
        self.assertEqual(result.contacts[0].employee.department,'인사부')

    def test_benefits_proposal_is_not_overridden_by_buying_words(self):
        for question in (
            '복리후생에 초콜릿 구매 건의하고 싶다',
            '복리 후생으로 초콜릿 구매를 제안하고 싶어요',
            '사내 간식 지원을 위해 구매를 건의하고 싶어요',
            '복리후생 초콜릿 구매 구매 구매 계약 구매 건의',
        ):
            with self.subTest(question=question):
                result=self.recommender.recommend(question,'Q')
                self.assertEqual(result.status,'recommended')
                self.assertTrue(all(item.employee.dept_id=='PAY' for item in result.contacts))
                self.assertNotIn('구매',result.contacts[0].matched_terms)

    def test_actual_procurement_intent_still_routes_to_contracts(self):
        for question in ('물품 구매 절차 문의','복지용 초콜릿 납품업체 선정과 입찰 진행 문의','구매 문의'):
            with self.subTest(question=question):
                result=self.recommender.recommend(question,'Q')
                self.assertTrue(result.contacts)
                self.assertTrue(all(item.employee.dept_id=='BUY' for item in result.contacts))

    def test_employment_contract_is_not_procurement(self):
        result=self.recommender.recommend('계약직 근로계약과 복리후생 문의','Q')
        self.assertEqual({item.employee.dept_id for item in result.contacts},{'HR','PAY'})

    def test_negated_department_and_topic_are_not_recommended(self):
        for question in ('공정계약실 말고 복지 담당자','계약 업무가 아니라 복리후생 문의'):
            with self.subTest(question=question):
                result=self.recommender.recommend(question,'Q')
                self.assertTrue(result.contacts)
                self.assertTrue(all(item.employee.dept_id=='PAY' for item in result.contacts))

    def test_weak_buying_followup_preserves_benefits_context(self):
        result=self.recommender.recommend('그럼 초콜릿 구매도 건의하고 싶어','Q',[
            {'role':'user','content':'복리후생 제도 문의'},
            {'role':'assistant','content':'복리후생 설명'},
        ])
        self.assertTrue(result.contacts)
        self.assertTrue(all(item.employee.dept_id=='PAY' for item in result.contacts))

    def test_new_topic_and_explicit_department_override_old_context(self):
        history=[{'role':'user','content':'복지 혜택 문의'}]
        for question in ('다른 질문인데 물품 구매 절차는?','공정계약실 담당자를 알려줘'):
            with self.subTest(question=question):
                result=self.recommender.recommend(question,'Q',history)
                self.assertTrue(all(item.employee.dept_id=='BUY' for item in result.contacts))
                self.assertTrue(result.contacts)

    def test_followup_does_not_jump_over_an_unrelated_topic(self):
        result=self.recommender.recommend('그럼 어디에 문의해?','Q',[
            {'role':'user','content':'연봉 문의'},
            {'role':'user','content':'화성 토양의 결정 구조는?'},
        ])
        self.assertEqual(result.status,'not_found')
        result=self.recommender.recommend('그럼 화성 토양의 결정 구조는?','Q',[
            {'role':'user','content':'연봉 문의'},
        ])
        self.assertEqual(result.status,'not_found')

    def test_unclear_proposal_requests_clarification(self):
        result=self.recommender.recommend('초콜릿 구매를 건의하고 싶다','Q')
        self.assertEqual(result.status,'not_found')
        self.assertEqual(result.contacts,[])

    def test_two_business_topics_include_both_departments(self):
        result=self.recommender.recommend('복리후생과 입찰 담당자를 둘 다 알려줘','Q')
        self.assertEqual({item.employee.dept_id for item in result.contacts},{'PAY','BUY'})

    def test_dedicated_benefits_department_is_preferred_when_present(self):
        class BenefitsDirectory(FakeDirectory):
            def departments(self):
                return [*super().departments(),DepartmentProfile(dept_id='WEL',dept_name='복지지원팀',dept_function='복리후생 제도 운영')]

            def contact_candidates(self,ids):
                candidates=super().contact_candidates(ids)
                if 'WEL' in ids:
                    for employee in ('W1','W2'):
                        candidates.append({'profile':UserProfile(employee_id=employee,name=employee,dept_id='WEL',
                            department='복지지원팀',work_email=employee+'@example.com',roles=['복지 실무담당자']),
                            'role_details':[{'role_category':'PROCESSOR'}]})
                return candidates

        result=ContactRecommender(BenefitsDirectory()).recommend('복리후생 초콜릿 구매 건의','Q')
        self.assertEqual(len(result.contacts),2)
        self.assertTrue(all(item.employee.dept_id=='WEL' for item in result.contacts))

    def test_benefits_fallback_uses_hr_when_payroll_has_no_contacts(self):
        directory=FakeDirectory()
        candidates=directory.contact_candidates
        directory.contact_candidates=lambda ids:[item for item in candidates(ids) if item['profile'].dept_id!='PAY']
        result=ContactRecommender(directory).recommend('복리후생 초콜릿 구매 건의','Q')
        self.assertEqual(result.status,'recommended')
        self.assertTrue(all(item.employee.dept_id=='HR' for item in result.contacts))

    def test_missing_routing_data_is_nonfatal_and_not_a_fake_contact(self):
        with patch('app.agent.escalation.settings',replace(settings,contact_routing_path=Path('missing-routing-config.json'))):
            with self.assertLogs('app.agent.escalation',level='WARNING'):
                result=self.recommender.recommend('연봉','Q')
        self.assertEqual(result.status,'unavailable')
        self.assertEqual(result.contacts,[])


class ContactEscalationServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner=asyncio.Runner()

    @classmethod
    def tearDownClass(cls):
        cls.runner.close()

    def service(self,repository,result):
        users=Mock();users.get.return_value=UserProfile(employee_id='Q',name='문의자')
        gateway=Mock(transport='mcp_test')
        gateway.list_tools=AsyncMock(return_value=[ToolDefinition(id='hr_employment',name='인사',description='인사 규정',data_path='')])
        gateway.execute=AsyncMock(return_value=result)
        service=ChatService(repository,users,tools=gateway)
        # 개발자 .env에 실제 n8n 주소가 있어도 테스트 이벤트를 외부에 보내지 않습니다.
        service.n8n.send_event=AsyncMock(return_value=DeliveryResult('sent'))
        service.contacts=ContactRecommender(FakeDirectory())
        service.ollama.choose_tools=AsyncMock(return_value=ToolDecision(tool_id='hr_employment'))
        return service

    def test_no_result_in_hr_tool_still_recommends_salary_duty_contacts(self):
        repository=MemoryConversationRepository();conversation=repository.create('Q')
        service=self.service(repository,ToolResult(tool_id='hr_employment',status='no_result',message='근거 없음'))
        response=self.runner.run(service.reply(conversation,ChatRequest(message='나 연봉 언제 오르지',employee_id='Q')))
        self.assertEqual(response.contact_escalation.status,'recommended')
        self.assertEqual(response.contact_escalation.contacts[0].employee.department,'급여부')
        self.assertEqual(response.context.answer_coverage,'missing')
        self.assertEqual(repository.get(conversation.id).messages[-1].contact_escalation,response.contact_escalation)

    def test_missing_benefits_evidence_recommends_welfare_related_contacts(self):
        repository=MemoryConversationRepository();conversation=repository.create('Q')
        service=self.service(repository,ToolResult(tool_id='hr_employment',status='no_result',message='근거 없음'))
        response=self.runner.run(service.reply(conversation,ChatRequest(
            message='복리후생에 초콜릿 구매 건의하고 싶다',employee_id='Q')))
        self.assertEqual(response.contact_escalation.status,'recommended')
        self.assertTrue(all(item.employee.dept_id=='PAY' for item in response.contact_escalation.contacts))

    def test_partial_answer_gets_contacts_and_direct_answer_does_not(self):
        for coverage in ['partial','direct']:
            with self.subTest(coverage=coverage):
                repository=MemoryConversationRepository();conversation=repository.create('Q')
                service=self.service(repository,ToolResult(tool_id='hr_employment',status='ok',message='조회',sources=[Source(document='규정.pdf',text='규정')]))
                async def generate(context):
                    context.answer_coverage=coverage
                    return '확인된 일반 기준입니다.'
                service.ollama.generate_answer=generate
                response=self.runner.run(service.reply(conversation,ChatRequest(message='연봉 인상일',employee_id='Q')))
                self.assertEqual(bool(response.contact_escalation.contacts),coverage=='partial')

    def test_model_validation_fallback_is_needs_review_with_contacts(self):
        repository=MemoryConversationRepository();conversation=repository.create('Q')
        service=self.service(repository,ToolResult(tool_id='hr_employment',status='ok',message='조회',sources=[Source(document='규정.pdf',text='규정')]))
        service.ollama._chat=AsyncMock(return_value='{"summary":"truncated')
        response=self.runner.run(service.reply(conversation,ChatRequest(message='연봉 인상일',employee_id='Q')))
        self.assertEqual(response.status,'needs_review')
        self.assertTrue(response.contact_escalation.contacts)

    def test_sqlite_restores_contact_cards_without_schema_migration(self):
        with tempfile.TemporaryDirectory() as temp:
            config=replace(settings,sqlite_path=Path(temp)/'chat.sqlite3')
            with patch('app.integrations.sqlite.settings',config):
                repository=SQLiteConversationRepository();conversation=repository.create('Q')
                service=self.service(repository,ToolResult(tool_id='hr_employment',status='no_result',message='없음'))
                response=self.runner.run(service.reply(conversation,ChatRequest(message='연봉 인상일',employee_id='Q')))
                restored=SQLiteConversationRepository().get(conversation.id)
                self.assertEqual(restored.messages[-1].contact_escalation,response.contact_escalation)
                self.assertEqual(restored.messages[0].contact_escalation.status,'not_needed')
