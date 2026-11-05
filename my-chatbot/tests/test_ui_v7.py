import json
import tempfile
import unittest
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import AsyncMock,Mock,patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes as core
from app.api.ui import router,QuestionRequest,chat_request
from app.agent.service import ChatService
from app.config import settings
from app.repositories.sqlite import SQLiteConversationRepository
from app.schemas import (UserProfile,Source,ToolDecision,ToolResult,AnswerContext,Message,
                         ContactEscalation,ContactRecommendation)


class V7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app=FastAPI();app.include_router(core.router,prefix='/api');app.include_router(router,prefix='/api')
        cls.client=TestClient(app);cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None,None,None)

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.config=replace(settings,sqlite_path=Path(temporary.name)/'app.sqlite3',n8n_webhook_url='',n8n_async=False,warm_up=False)
        for target in ['app.integrations.sqlite.settings','app.agent.service.settings']:
            item=patch(target,self.config);item.start();self.addCleanup(item.stop)
        self.repository=SQLiteConversationRepository()
        self.profile=UserProfile(employee_id='A',name='가상 사원',grade='3직급',department='인사부')
        users=Mock();users.get.side_effect=lambda employee:self.profile.model_copy(update={'employee_id':employee}) if employee in ['A','B'] else None
        tools=Mock(ready=True,transport='test')
        tools.list_tools=AsyncMock(return_value=[tool.definition for tool in core.TOOLS.values()])
        tools.execute=AsyncMock(return_value=ToolResult(tool_id='work_labor',status='ok',message='검색됨',sources=[Source(document='취업규칙.pdf',page=3,text='전산시스템의 근태계로 전자결재 승인받습니다.',chunk_id='a'*24+':000001')]))
        self.service=ChatService(self.repository,users,tools=tools)
        self.service.ollama.choose_tools=AsyncMock(return_value=ToolDecision(tool_id='work_labor'))
        async def generate(context,on_preview=None):
            if on_preview:await on_preview('작성 중인 미리보기')
            context.answer_coverage='direct'
            return '근태계를 제출하고 **전자결재 승인**을 받으세요.\n- 전산시스템 양식을 사용합니다.'
        self.service.ollama.generate_answer=generate
        for name,value in [('repository',self.repository),('service',self.service)]:
            item=patch.object(core,name,value);item.start();self.addCleanup(item.stop)

    def create(self,employee='A'):
        response=self.client.post('/api/conversations',json={'employee_id':employee})
        self.assertEqual(response.status_code,201)
        return response.json()['id']

    def ask(self,session=None,**fields):
        return self.client.post('/api/hr/question',json={'employee_id':'A','session_id':session or self.create(),'question':'연차 신청 방법','category_id':'work_leave_labor',**fields})

    def test_employee_uses_real_repository_shape_and_rejects_unknown_id(self):
        response=self.client.post('/api/hr/employee',json={'employee_id':'A'}).json()
        self.assertEqual(response['employee']['name'],'가상 사원')
        self.assertEqual(self.client.post('/api/hr/employee',json={'employee_id':'UNKNOWN'}).status_code,404)

    def test_question_response_and_saved_turn_restore(self):
        session=self.create();answer=self.ask(session)
        self.assertEqual(answer.status_code,200)
        data=answer.json();self.assertEqual(data['session_id'],session)
        self.assertIn('전자결재',data['answer']);self.assertTrue(data['steps']);self.assertTrue(data['context'])
        self.assertEqual(data['sources'][0]['page'],3)
        detail=self.client.post('/api/hr/conversation',json={'employee_id':'A','session_id':session}).json()
        self.assertEqual(detail['turns'][0]['request_id'],data['request_id'])
        self.assertEqual(detail['turns'][0]['answer'],data['answer'])

    def test_stream_translates_replacement_previews_and_keeps_final_contract(self):
        response=self.client.post('/api/hr/question/stream',json={'employee_id':'A','session_id':self.create(),'question':'연차 신청','category_id':'work_leave_labor'})
        self.assertEqual(response.status_code,200)
        events=[]
        for block in response.text.strip().split('\n\n'):
            lines=block.splitlines();events.append((lines[0],json.loads(lines[1][6:])))
        self.assertTrue(any(key=='event: delta' and payload['replace'] is True for key,payload in events))
        self.assertEqual(events[-1][0],'event: final')
        self.assertIn('request_id',events[-1][1]);self.assertIn('sources',events[-1][1])

    def test_history_search_is_owned_and_does_not_expose_other_employees(self):
        own=self.create();self.ask(own)
        other=self.create('B')
        response=self.client.post('/api/hr/history',json={'employee_id':'A','search':'연차'}).json()
        self.assertEqual([item['session_id'] for item in response['conversations']],[own])
        self.assertEqual(self.client.post('/api/hr/conversation',json={'employee_id':'A','session_id':other}).status_code,403)
        self.assertEqual(self.client.post('/api/hr/retry',json={'employee_id':'A','session_id':other}).status_code,403)

    def test_stars_preserve_exact_score_and_issue_and_close_chat(self):
        session=self.create();answer=self.ask(session).json()
        response=self.client.post('/api/hr/feedback',json={'employee_id':'A','session_id':session,'request_id':answer['request_id'],'rating':4,'error_type':'wrong_source','comment':'출처 확인 부탁해요'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['score'],4)
        detail=self.client.post('/api/hr/conversation',json={'employee_id':'A','session_id':session}).json()
        self.assertEqual(detail['conversation']['status'],'closed')
        self.assertEqual(detail['conversation']['end_result']['score'],4)
        from app.integrations.sqlite import connection_scope
        with connection_scope() as connection:payload=json.loads(connection.execute('SELECT payload FROM webhook_events').fetchone()['payload'])
        self.assertEqual(payload['satisfaction_score'],4);self.assertEqual(payload['error_type'],'wrong_source')
        self.assertEqual(payload['message_id'],str(self.repository.get(session).messages[0].id))
        self.assertEqual(self.ask(session).status_code,409)
        again=self.client.post('/api/hr/feedback',json={'employee_id':'A','session_id':session,'request_id':answer['request_id'],'rating':1}).json()
        self.assertEqual(again['score'],4)

    def test_foreign_feedback_answer_and_invalid_stars_are_rejected(self):
        session=self.create()
        response=self.client.post('/api/hr/feedback',json={'employee_id':'A','session_id':session,'request_id':str(uuid4()),'rating':5})
        self.assertEqual(response.status_code,404)
        for score in [0,6]:
            response=self.client.post('/api/hr/feedback',json={'employee_id':'A','session_id':session,'request_id':str(uuid4()),'rating':score})
            self.assertEqual(response.status_code,422)

    def test_explicit_form_arguments_override_model_guess_and_reach_tool(self):
        self.service.ollama.choose_tools=AsyncMock(return_value=ToolDecision(tool_id='work_labor'))
        response=self.ask(input_data={'task':'leave_period','start_date':'2026-11-09','end_date':'2026-11-11','requested_days':2.5})
        self.assertEqual(response.status_code,200)
        request=self.service.tools.execute.await_args.args[1]
        self.assertEqual(request.arguments['requested_days'],2.5)
        self.assertEqual(request.employee_id,'A')

    def test_travel_form_maps_native_trip_and_does_not_override_employee_profile(self):
        request=chat_request(QuestionRequest(employee_id='A',question='예상 여비',input_data={'task':'travel_estimate','trip_type':'domestic','destination_city':'부산','start_date':'2026-11-06','end_date':'2026-11-07','distance_km':600,'same_city':False}))
        self.assertEqual(request.tool_id,'travel_expenses')
        self.assertEqual(request.arguments.trip['destination_city'],'부산')
        self.assertEqual(request.employee_id,'A')

    def test_contacts_and_restored_recommendations_use_profile_fields(self):
        profile=self.profile.model_copy(update={'employee_id':'C','name':'담당자','department':'급여부','extension_number':'2115','work_email':'c@example.com','image_url':'/api/users/C/photo'})
        escalation=ContactEscalation(status='recommended',contacts=[ContactRecommendation(employee=profile,reason='급여 업무')])
        self.service.contacts=Mock();self.service.contacts.recommend.return_value=escalation
        response=self.client.post('/api/hr/contact',json={'employee_id':'A','category_id':'payroll'}).json()
        self.assertEqual(response['contacts'][0]['extension'],'2115')
        self.assertEqual(response['contacts'][0]['email'],'c@example.com')

    def test_source_path_rejects_arbitrary_file_names(self):
        self.assertEqual(self.client.get('/api/hr/source/secrets.env').status_code,404)

    def test_invalid_form_values_are_422_instead_of_server_errors(self):
        self.assertEqual(self.ask(input_data={'task':'leave_period','requested_days':-2}).status_code,422)

    def test_restored_status_is_preserved_for_answers_with_contact_cards(self):
        session=self.create();self.ask(session)
        result=self.client.post('/api/hr/conversation',json={'employee_id':'A','session_id':session}).json()
        self.assertEqual(result['turns'][0]['status'],'answered')
