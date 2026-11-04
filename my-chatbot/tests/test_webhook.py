"""가상 사용자 데이터만 로컬 HTTP 수신기로 보내는 종료 웹훅 통합 검사."""

import asyncio
import json
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.agent.service import ChatService
from app.config import settings
from app.integrations.n8n import N8nClient
from app.repositories.sqlite import SQLiteConversationRepository
from app.schemas import AnswerContext, EndRequest, Message, UserProfile, ChatRequest, ToolDefinition, ToolDecision, ToolResult


class WebhookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.received = []
        cls.status_code = 200
        cls.delay = 0
        cls.response_body = {'ok':True}
        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                cls.received.append((self.path,self.headers.get('Idempotency-Key'),payload))
                time.sleep(cls.delay)
                self.send_response(cls.status_code)
                self.send_header('Content-Type','application/json')
                self.end_headers()
                try:
                    self.wfile.write(json.dumps(cls.response_body).encode('utf-8'))
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                    pass
            def log_message(self,*args):
                pass
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),Receiver)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.received.clear()
        type(self).status_code = 200
        type(self).delay = 0
        type(self).response_body = {'ok':True}
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.config = replace(settings,sqlite_path=Path(temp.name)/'app.sqlite3',
                              n8n_webhook_url=f'http://127.0.0.1:{self.server.server_port}/webhook/test-end',
                              n8n_message_limit=2,n8n_message_max_chars=100,n8n_timeout=1)
        for target in ('app.integrations.sqlite.settings','app.integrations.n8n.settings','app.agent.service.settings'):
            item=patch(target,self.config); item.start(); self.addCleanup(item.stop)
        self.repository = SQLiteConversationRepository()
        self.conversation = self.repository.create('FAKE-001')
        self.users=Mock()
        self.users.get.return_value=UserProfile(employee_id='FAKE-001',name='가상 직원',department='가상 부서')
        self.service=ChatService(self.repository,self.users)
        self.runner=asyncio.Runner()
        self.addCleanup(self.runner.close)

    def populate(self):
        messages=[Message(id=uuid4(),role=role,content=text,created_at=datetime.now(timezone.utc)) for role,text in (
            ('user','첫 질문'),('assistant','첫 답변'),('user','마지막 질문'),('assistant','가상 답변'*100))]
        self.repository.append_turn(self.conversation.id,messages,AnswerContext(employee_id='FAKE-001',question='질문'),None)

    def test_end_posts_compact_user_feedback_and_latest_messages_once(self):
        self.populate()
        result=self.runner.run(self.service.end(self.conversation,EndRequest(rating='helpful',comment='좋아요')))
        self.assertEqual(result.webhook_status,'sent')
        self.assertEqual(len(self.received),1)
        path,key,payload=self.received[0]
        self.assertEqual(path,'/webhook/test-end')
        self.assertEqual(key,str(result.event_id))
        self.assertEqual(payload['event'],'session_end')
        self.assertEqual(payload['session_id'],str(self.conversation.id))
        self.assertEqual(payload['session_status'],'CLOSED')
        self.assertEqual(payload['user']['name'],'가상 직원')
        self.assertEqual(payload['rating'],'helpful')
        self.assertEqual(payload['message_count'],4)
        self.assertEqual(payload['turn_count'],2)
        self.assertEqual(len(payload['messages']),2)
        self.assertEqual(payload['messages'][0]['content'],'마지막 질문')
        self.assertEqual(len(payload['messages'][1]['content']),100)
        self.assertTrue(payload['history_truncated'])
        self.assertNotIn('context',str(payload))
        again=self.runner.run(self.service.end(self.conversation,EndRequest(rating='unhelpful')))
        self.assertEqual(again.event_id,result.event_id)
        self.assertEqual(again.rating,'helpful')
        self.assertEqual(len(self.received),1)
        from app.integrations.sqlite import connection_scope
        with connection_scope() as c:
            row=c.execute('SELECT status,attempts FROM webhook_events').fetchone()
            self.assertEqual((row['status'],row['attempts']),('sent',1))

    def test_session_end_uses_sheet_column_names(self):
        self.populate()
        self.runner.run(self.service.end(self.conversation,EndRequest(rating='helpful',comment='좋아요')))
        payload=self.received[0][2]
        self.assertEqual(payload['satisfaction_score'],5)
        self.assertEqual(payload['satisfaction_comment'],'좋아요')
        self.assertTrue(payload['started_at'] and payload['ended_at'])
        self.assertEqual(payload['session_status'],'CLOSED')

    def test_answer_payload_matches_qa_sheet_columns_and_escalation_handler(self):
        from app.integrations.n8n import answer_sheet_fields
        from app.schemas import ContactEscalation, ContactRecommendation
        employee=UserProfile(employee_id='HR001',name='김담당',department='인사팀',work_email='hr@example.com')
        response=Mock(status='no_result',sources=[],tool_results=[],
                      contact_escalation=ContactEscalation(status='recommended',contacts=[ContactRecommendation(employee=employee,matched_terms=[],duty_description='',reason='')]))
        fields=answer_sheet_fields(response,'Q-AT','A-AT')
        self.assertEqual(fields,{'question_at':'Q-AT','answer_at':'A-AT','answer_status':'ESCALATED','answer_source':'HR_ROUTING',
                                 'handler_id':'HR001','handler_name':'김담당','handler_department':'인사팀','handler_contact':'hr@example.com'})
        rag=Mock(status='answered',sources=[object()],tool_results=[],contact_escalation=ContactEscalation())
        fields=answer_sheet_fields(rag,'Q','A')
        self.assertEqual((fields['answer_status'],fields['answer_source'],fields['handler_id']),('ANSWERED','RAG',''))

    def test_failure_keeps_feedback_and_retry_reuses_the_same_event(self):
        type(self).status_code=503
        result=self.runner.run(self.service.end(self.conversation,EndRequest(rating='neutral')))
        self.assertEqual(result.webhook_status,'failed')
        saved=self.repository.get(self.conversation.id)
        self.assertEqual(saved.status,'closed')
        self.assertEqual(saved.end_result.rating,'neutral')
        type(self).status_code=200
        retried=self.runner.run(self.service.deliver_end_event(self.conversation.id))
        self.assertEqual(retried.webhook_status,'sent')
        self.assertEqual(self.received[0][1],self.received[1][1])
        self.assertEqual(retried.event_id,result.event_id)
        self.runner.run(self.service.deliver_end_event(self.conversation.id))
        self.assertEqual(len(self.received),2)

    def test_blank_url_saves_without_network_and_can_be_sent_after_configuration(self):
        blank=replace(self.config,n8n_webhook_url='')
        with patch('app.agent.service.settings',blank),patch('app.integrations.n8n.settings',blank):
            result=self.runner.run(self.service.end(self.conversation,EndRequest()))
        self.assertEqual(result.webhook_status,'not_configured')
        self.assertEqual(self.received,[])
        self.assertEqual(self.runner.run(self.service.deliver_end_event(self.conversation.id)).webhook_status,'sent')

    def test_timeout_is_recorded_as_failure(self):
        type(self).delay=0.15
        with patch('app.integrations.n8n.settings',replace(self.config,n8n_timeout=0.02)):
            result=self.runner.run(N8nClient().send_conversation_ended({'event_id':'fake-timeout'}))
        self.assertEqual(result.status,'failed')
        self.assertEqual(result.error,'timeout')

    def test_simultaneous_end_requests_send_a_single_event(self):
        async def end_twice():
            return await asyncio.gather(*(self.service.end(self.conversation,EndRequest(rating='helpful')) for _ in range(2)))
        results=self.runner.run(end_twice())
        self.assertEqual(results[0].event_id,results[1].event_id)
        self.assertEqual(len(self.received),1)

    def setup_chat(self):
        self.service.tools=Mock(transport='local_test')
        self.service.tools.list_tools=AsyncMock(return_value=[ToolDefinition(id='work_labor',name='근무',description='가상 규정',data_path='')])
        self.service.tools.execute=AsyncMock(return_value=ToolResult(tool_id='work_labor',status='ok',message='조회',data={'balance':5}))
        self.service.ollama.choose_tools=AsyncMock(return_value=ToolDecision(tool_id='work_labor'))
        async def generate(context):
            # 질문은 모델 호출 전에 이미 수신되어 있어야 합니다.
            self.assertEqual(self.received[-1][2]['event'],self.config.n8n_event_question)
            context.answer_coverage='direct'
            return '가상 답변: 잔여 휴가는 5일입니다. 😊'
        self.service.ollama.generate_answer=generate

    def test_lifecycle_posts_in_order_with_correlated_ids_and_utf8(self):
        self.setup_chat()
        conversation=self.runner.run(self.service.start_conversation('FAKE-001'))
        response=self.runner.run(self.service.reply(conversation,ChatRequest(employee_id='FAKE-001',message='연차 신청 절차는?')))
        self.runner.run(self.service.end(conversation,EndRequest(rating='helpful',comment='도움이 됐어요')))
        start,question,answer,end=[item[2] for item in self.received]
        self.assertEqual([item['event'] for item in (start,question,answer,end)],['session_start','question','answer','session_end'])
        self.assertTrue(all(item['session_id']==str(conversation.id) and item['employee_id']=='FAKE-001' for item in (start,question,answer,end)))
        self.assertEqual(start['session_status'],'OPEN')
        self.assertEqual(start['user']['name'],'가상 직원')
        self.assertEqual(question['question'],'연차 신청 절차는?')
        self.assertEqual(question['answer_status'],'PENDING')
        self.assertEqual(question['message_id'],answer['message_id'])
        self.assertEqual(answer['answer'],response.answer.replace('**',''))  # 시트에는 강조 표시 없이 저장
        self.assertEqual(answer['answer_status'],'ANSWERED')
        saved=self.repository.get(conversation.id)
        self.assertEqual(str(saved.messages[0].id),question['message_id'])
        self.assertEqual(str(saved.messages[1].id),answer['answer_message_id'])
        self.assertEqual(end['rating'],'helpful')
        self.assertEqual(end['comment'],'도움이 됐어요')
        self.assertEqual(end['session_status'],'CLOSED')
        self.assertTrue(all(key==payload['event_id'] for _,key,payload in self.received))
        self.assertEqual(len({item['event_id'] for item in (start,question,answer,end)}),4)
        self.assertTrue(all(item.status=='sent' for item in response.webhook_events))
        self.assertNotIn('sources',answer)
        self.assertNotIn('context',answer)
        # 조회·복원 자체는 새 이벤트를 생성하지 않습니다.
        self.repository.get(conversation.id)
        self.assertEqual(len(self.received),4)

    def test_failed_n8n_does_not_block_chat_or_local_storage(self):
        self.setup_chat()
        type(self).status_code=503
        with self.assertLogs('app.integrations.n8n',level='WARNING'):
            conversation=self.runner.run(self.service.start_conversation('FAKE-001'))
            response=self.runner.run(self.service.reply(conversation,ChatRequest(employee_id='FAKE-001',message='연차?')))
        self.assertTrue(all(item.status=='failed' for item in response.webhook_events))
        self.assertEqual(len(self.repository.get(conversation.id).messages),2)
        self.assertIn('가상 답변',response.answer)

    def test_model_failure_posts_failed_answer_for_the_pending_question(self):
        from app.errors import ModelUnavailable
        self.setup_chat()
        self.service.ollama.generate_answer=AsyncMock(side_effect=ModelUnavailable('모델 연결 실패'))
        conversation=self.runner.run(self.service.start_conversation('FAKE-001'))
        with self.assertRaises(ModelUnavailable):
            self.runner.run(self.service.reply(conversation,ChatRequest(employee_id='FAKE-001',message='연차?')))
        _,question,answer=[item[2] for item in self.received]
        self.assertEqual(answer['message_id'],question['message_id'])
        self.assertEqual(answer['answer_status'],'FAILED')
        self.assertEqual(answer['answer'],'')
        self.assertEqual(self.repository.get(conversation.id).messages,[])

    def test_receiver_ok_false_is_a_failure_even_with_http_200(self):
        type(self).response_body={'ok':False}
        result=self.runner.run(N8nClient().send_event({'event_id':'rejected','event':'question'}))
        self.assertEqual((result.status,result.error),('failed','receiver_rejected'))

    def test_blank_url_skips_all_lifecycle_requests(self):
        self.setup_chat()
        blank=replace(self.config,n8n_webhook_url='')
        self.service.ollama.generate_answer=AsyncMock(return_value='가상 답변')
        with patch('app.agent.service.settings',blank),patch('app.integrations.n8n.settings',blank):
            conversation=self.runner.run(self.service.start_conversation('FAKE-001'))
            response=self.runner.run(self.service.reply(conversation,ChatRequest(employee_id='FAKE-001',message='연차?')))
        self.assertEqual(self.received,[])
        self.assertTrue(all(item.status=='not_configured' for item in response.webhook_events))

    def test_event_names_are_configurable_including_saved_end_payload(self):
        custom=replace(self.config,n8n_event_session_start='start',n8n_event_question='ask',n8n_event_answer='reply',n8n_event_session_end='feedback')
        with patch('app.agent.service.settings',custom):
            self.setup_chat()
            self.service.ollama.generate_answer=AsyncMock(return_value='가상 답변')
            conversation=self.runner.run(self.service.start_conversation('FAKE-001'))
            self.runner.run(self.service.reply(conversation,ChatRequest(employee_id='FAKE-001',message='연차?')))
            self.runner.run(self.service.end(conversation,EndRequest()))
        self.assertEqual([item[2]['event'] for item in self.received],['start','ask','reply','feedback'])


class AsyncDeliveryTests(unittest.TestCase):
    def test_logs_are_sent_in_background_but_in_order_without_blocking(self):
        import asyncio
        from dataclasses import replace
        from unittest.mock import AsyncMock, Mock, patch
        from app.agent.service import ChatService
        from app.config import settings
        from app.integrations.n8n import DeliveryResult
        from app.repositories.memory import MemoryConversationRepository

        order = []

        async def send(payload):
            if payload['event'] == 'question':
                await asyncio.sleep(0.05)  # 앞선 이벤트가 느려도 뒤 이벤트가 먼저 도착하면 안 됩니다.
            order.append(payload['event'])
            return DeliveryResult('sent')

        async def scenario():
            service = ChatService(MemoryConversationRepository(), Mock())
            service.n8n.send_event = AsyncMock(side_effect=send)
            config = replace(settings, n8n_webhook_url='http://127.0.0.1:9/hook', n8n_async=True)
            with patch('app.agent.service.settings', config):
                first = await service.send_log({'event': 'question', 'event_id': str(uuid4()), 'session_id': 'S1'})
                second = await service.send_log({'event': 'answer', 'event_id': str(uuid4()), 'session_id': 'S1'})
                self.assertEqual((first.status, second.status), ('queued', 'queued'))
                self.assertEqual(order, [])  # 호출자는 전송을 기다리지 않습니다.
                await service.flush('S1')
            self.assertEqual(order, ['question', 'answer'])
            self.assertFalse(service._pending)

        asyncio.run(scenario())
