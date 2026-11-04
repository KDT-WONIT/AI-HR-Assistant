import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.agent.service import ChatService
from app.mcp.client import LocalToolGateway
from app.errors import StorageUnavailable
from app.integrations.ollama import OllamaClient
from app.main import app
from app.repositories.memory import MemoryConversationRepository
from app.repositories.users import FileUserRepository, load_profiles
from app.schemas import AnswerContext, UserProfile, ToolDecision, Source


class UserContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'users.json'
        self.write_profiles()
        self.users = FileUserRepository(self.path)
        from app.api import routes
        repository = MemoryConversationRepository()
        self.patch_repo = patch.object(routes, 'repository', repository)
        self.patch_service = patch.object(routes, 'service', ChatService(repository, self.users, tools=LocalToolGateway()))
        self.patch_repo.start()
        self.patch_service.start()
        self.addCleanup(self.patch_repo.stop)
        self.addCleanup(self.patch_service.stop)
        routes.service.ollama.choose_tools = AsyncMock(return_value=ToolDecision(tool_id='work_labor'))
        routes.service.ollama.generate_answer = AsyncMock(return_value='테스트 답변')
        rag = patch('app.tools.execution.RagService.search', AsyncMock(return_value=[Source(document='fixture.pdf', text='규정')]))
        business = patch('app.tools.execution.business_data', return_value=({}, None))
        for item in (rag, business):
            item.start()
            self.addCleanup(item.stop)

    def write_profiles(self, department='개발팀'):
        self.path.write_text(json.dumps([
            {'employee_id': 'USER-A', 'name': '사용자 A', 'department': department, 'job_title': '사원', 'hired_at': '2025-01-02'},
            {'employee_id': 'USER-B', 'name': '다른 사용자', 'department': '인사팀'},
        ], ensure_ascii=False), encoding='utf-8')

    def test_id_lookup_does_not_return_other_user(self):
        response = self.client.get('/api/users/USER-A')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['profile']['department'], '개발팀')
        self.assertNotIn('다른 사용자', response.text)
        self.assertEqual(self.client.get('/api/users/UNKNOWN').json(), {
            'employee_id': 'UNKNOWN', 'status': 'not_found', 'profile': None,
        })

    def test_profile_and_history_reach_context_and_refresh(self):
        first = self.client.post('/api/chat', json={'employee_id': 'USER-A', 'message': '연차 규정'})
        self.assertEqual(first.status_code, 200)
        data = first.json()
        self.assertEqual(data['context']['user_profile_status'], 'found')
        self.assertEqual(data['context']['user_profile']['name'], '사용자 A')
        self.assertNotIn('다른 사용자', first.text)
        self.write_profiles(department='연구팀')
        second = self.client.post('/api/chat', json={
            'employee_id': 'USER-A', 'conversation_id': data['conversation_id'], 'message': '다음 질문',
        }).json()
        self.assertEqual(second['context']['user_profile']['department'], '연구팀')
        self.assertEqual(len(second['context']['history']), 2)

    def test_unknown_user_is_explicit_not_invented(self):
        response = self.client.post('/api/chat', json={'employee_id': 'UNKNOWN', 'message': '연차 규정'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['context']['user_profile'])
        self.assertEqual(response.json()['context']['user_profile_status'], 'not_found')

    def test_broken_user_data_fails_without_partial_chat_record(self):
        conversation_id = self.client.post('/api/conversations', json={'employee_id': 'USER-A'}).json()['id']
        self.path.write_text('broken json', encoding='utf-8')
        response = self.client.post('/api/chat', json={
            'employee_id': 'USER-A', 'conversation_id': conversation_id, 'message': '질문',
        })
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get(f'/api/conversations/{conversation_id}').json()['messages'], [])

    def test_duplicate_ids_and_unapproved_fields_are_rejected(self):
        for profiles in (
            [{'employee_id': 'A', 'name': 'a'}, {'employee_id': 'A', 'name': 'b'}],
            [{'employee_id': 'A', 'name': 'a', 'unapproved_field': 'do not forward'}],
        ):
            self.path.write_text(json.dumps(profiles), encoding='utf-8')
            with self.assertRaises(StorageUnavailable):
                load_profiles(self.path)

    def test_ollama_payload_includes_only_selected_profile(self):
        profile = UserProfile(employee_id='USER-A', name='사용자 A', department='개발팀')
        context = AnswerContext(question='질문', employee_id='USER-A', user_profile=profile, user_profile_status='found')
        messages = OllamaClient.build_messages(context)
        data = json.loads(messages[-1]['content'].split('## 사용자 정보\n```json\n')[1].split('\n```')[0])
        self.assertEqual(data['user_profile']['employee_id'], 'USER-A')
        self.assertEqual(data['user_profile']['department'], '개발팀')
        self.assertEqual(data['user_profile_status'], 'found')


if __name__ == '__main__':
    unittest.main()
