"""외부 서비스를 호출하지 않는 모의 모드 API 통합 테스트."""

import unittest
from dataclasses import replace
from uuid import uuid4
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.tools.registry import TOOLS
from app.agent.service import ChatService
from app.mcp.client import LocalToolGateway
from app.repositories.memory import MemoryConversationRepository
from app.repositories.users import FileUserRepository
from app.schemas import Source, ToolDecision, UserProfile


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        from app.api import routes
        repository = MemoryConversationRepository()
        self.service = ChatService(repository, FileUserRepository(Path('nonexistent-test-users.json')), tools=LocalToolGateway())
        self.service.ollama.choose_tools = AsyncMock(return_value=ToolDecision(tool_id='work_labor'))
        self.service.ollama.generate_answer = AsyncMock(return_value='테스트 답변')
        self.rag = AsyncMock(return_value=[Source(document='fixture.pdf', page=1, text='검증용 규정', distance=0.2)])
        for item in (patch.object(routes, 'repository', repository), patch.object(routes, 'service', self.service),
                     patch('app.agent.service.settings',replace(settings,n8n_webhook_url='')),
                     patch('app.tools.execution.RagService.search', self.rag),
                     patch('app.tools.execution.business_data', return_value=({}, None))):
            item.start()
            self.addCleanup(item.stop)

    def create(self):
        response = self.client.post("/api/conversations", json={"employee_id": "TEST-001"})
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def test_full_pipeline_passes_profile_rag_and_history_to_answer_model(self):
        profile = UserProfile(employee_id='TEST-001',name='테스트 직원',department='개발팀')
        with patch.object(self.service.users, 'get', return_value=profile):
            conversation_id = self.create()
            self.client.post('/api/chat',json={'message':'연차 규정','conversation_id':conversation_id})
            response = self.client.post('/api/chat',json={'message':'신청 절차도 알려줘','conversation_id':conversation_id})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['answer'],'테스트 답변')
        context = self.service.ollama.generate_answer.await_args.args[0]
        self.assertEqual(context.question,'신청 절차도 알려줘')
        self.assertEqual(context.user_profile.department,'개발팀')
        self.assertEqual(len(context.history),2)
        self.assertEqual(context.sources[0].document,'fixture.pdf')
        self.assertEqual(context.tool_results[0].tool_id,'work_labor')
        self.assertEqual(self.service.ollama.choose_tools.await_args.kwargs['history'],[{'role':'user','content':'연차 규정'}])
        stored = self.client.get('/api/conversations/'+conversation_id).json()['messages']
        self.assertEqual(len(stored),4)
        self.assertEqual(stored[-1]['content'],response.json()['answer'])

    def test_frontend_assets_and_catalog(self):
        for path in ("/", "/static/css/styles.css", "/static/js/chat.js", "/static/js/api.js", "/openapi.json"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        tools = self.client.get("/api/tools").json()
        self.assertEqual({tool['id'] for tool in tools}, set(TOOLS))
        health = self.client.get("/api/health").json()
        self.assertEqual(health["storage"], 'memory')
        self.assertEqual(health["mode"], settings.mode)

    def test_lifecycle_events_cover_explicit_and_implicit_session_creation(self):
        from app.integrations.n8n import DeliveryResult
        sender=AsyncMock(return_value=DeliveryResult('sent'))
        with (patch('app.agent.service.settings',replace(settings,n8n_webhook_url='http://local-test.invalid/hook')),
              patch.object(self.service.n8n,'send_event',sender)):
            explicit=self.create()
            response=self.client.post('/api/chat',json={'message':'연차 규정','conversation_id':explicit})
            self.assertEqual(response.status_code,200)
            self.assertEqual([call.args[0]['event'] for call in sender.await_args_list],['session_start','question','answer'])
            sender.reset_mock()
            response=self.client.post('/api/chat',json={'message':'연차 규정'})
            self.assertEqual(response.status_code,200)
            self.assertEqual([call.args[0]['event'] for call in sender.await_args_list],['session_start','question','answer'])
            self.assertEqual(len(response.json()['webhook_events']),3)

    def test_mcp_error_is_reported_and_does_not_save_a_partial_turn(self):
        from app.errors import MCPUnavailable
        conversation_id = self.create()
        with patch.object(self.service.tools,'execute',AsyncMock(side_effect=MCPUnavailable('MCP 연결 확인 필요'))):
            response = self.client.post('/api/chat',json={'message':'규정?', 'conversation_id':conversation_id})
        self.assertEqual(response.status_code,503)
        self.assertEqual(self.client.get('/api/conversations/'+conversation_id).json()['messages'],[])

    def test_webhook_retry_requires_an_ended_conversation(self):
        conversation_id = self.create()
        response = self.client.post(f'/api/conversations/{conversation_id}/webhook/retry')
        self.assertEqual(response.status_code,409)

    def test_each_tool_can_be_called_without_fabricated_data(self):
        for tool_id in TOOLS:
            with self.subTest(tool=tool_id):
                response = self.client.post("/api/chat", json={"message": "분야 테스트", "tool_id": tool_id})
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["tools_used"], [tool_id])
                self.assertEqual(data["tool_results"][0]["status"], "ok")
                self.assertEqual(data["tool_results"][0]["data"], {})
                self.assertEqual(data['sources'][0]['document'], 'fixture.pdf')

    def test_multiple_tools_and_history(self):
        conversation_id = self.create()
        first = self.client.post("/api/chat", json={
            "message": "연차와 출장 여비 규정을 알려주세요", "conversation_id": conversation_id,
        }).json()
        self.assertEqual(first["tools_used"], ['work_labor'])
        self.assertEqual(first["context"]["history"], [])
        second = self.client.post("/api/chat", json={
            "message": "그중 연차부터 알려줘", "conversation_id": conversation_id,
        }).json()
        self.assertEqual(len(second["context"]["history"]), 2)
        conversation = self.client.get(f"/api/conversations/{conversation_id}").json()
        self.assertEqual(len(conversation["messages"]), 4)
        self.assertEqual(conversation["messages"][-1]["id"], second["message_id"])

    def test_unknown_question_does_not_default_to_fake_policy(self):
        self.rag.return_value = []
        data = self.client.post("/api/chat", json={"message": "안녕하세요"}).json()
        self.assertEqual(data["tools_used"], ['work_labor'])
        self.assertEqual(data["sources"], [])
        self.assertEqual(data["status"], "no_result")
        self.service.ollama.generate_answer.assert_not_awaited()

    def test_validation_and_missing_conversation(self):
        for payload in ({"message": "  "}, {"message": "a" * 4001}, {"message": "test", "tool_id": "missing"}, {"message": "test", "conversation_id": "bad"}):
            self.assertEqual(self.client.post("/api/chat", json=payload).status_code, 422)
        self.assertEqual(self.client.get(f"/api/conversations/{uuid4()}").status_code, 404)

    def test_employee_mismatch(self):
        conversation_id = self.create()
        self.assertEqual(self.client.post("/api/chat", json={
            "conversation_id": conversation_id, "employee_id": "TEST-OTHER", "message": "연차",
        }).status_code, 409)
        self.assertEqual(self.client.get(f"/api/conversations/{conversation_id}").json()["messages"], [])

    def test_end_is_idempotent_and_closes_chat(self):
        conversation_id = self.create()
        path = f"/api/conversations/{conversation_id}/end"
        first = self.client.post(path, json={"rating": "helpful", "comment": "확인"})
        self.assertEqual(first.status_code, 200)
        data = first.json()
        self.assertIn(data["webhook_status"], {"not_configured", "not_implemented"})
        repeated = self.client.post(path, json={"rating": "unhelpful"})
        self.assertEqual(data, repeated.json())
        self.assertEqual(self.client.post("/api/chat", json={
            "message": "연차", "conversation_id": conversation_id,
        }).status_code, 409)
        conversation = self.client.get(f"/api/conversations/{conversation_id}").json()
        self.assertEqual(conversation["status"], "closed")
        self.assertEqual(conversation["end_result"]["rating"], "helpful")

    def test_invalid_feedback_does_not_close_chat(self):
        conversation_id = self.create()
        response = self.client.post(f"/api/conversations/{conversation_id}/end", json={"rating": "invalid"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(f"/api/conversations/{conversation_id}").json()["status"], "open")

    def test_history_is_limited_and_isolated_by_session(self):
        first, other = self.create(), self.create()
        self.client.post('/api/chat', json={'conversation_id': other, 'message': '다른 세션의 비밀 질문'})
        for index in range(7):
            self.client.post('/api/chat', json={'conversation_id': first, 'message': f'질문 {index}'})
        response = self.client.post('/api/chat', json={'conversation_id': first, 'message': '현재 질문'})
        history = response.json()['context']['history']
        self.assertEqual(len(history), 10)
        self.assertEqual([item['content'] for item in history if item['role'] == 'user'], [f'질문 {index}' for index in range(2, 7)])
        self.assertTrue(all('다른 세션의 비밀 질문' not in item['content'] for item in history))
        self.assertTrue(all('현재 질문' != item['content'] for item in history))


if __name__ == "__main__":
    unittest.main()
