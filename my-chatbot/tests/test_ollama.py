"""Postman 로컬 Ollama 시뮬레이션을 실제 HTTP로 호출하는 통합 테스트."""

import asyncio
import os
import unittest
from dataclasses import replace
from unittest.mock import patch
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx

from app.agent.service import ChatService
from app.mcp.client import LocalToolGateway
from app.config import settings
from app.errors import ModelUnavailable
from app.integrations.ollama import OllamaClient
from app.integrations.mysql import connection_scope
from app.repositories.memory import MemoryConversationRepository
from app.repositories.mysql import MySQLConversationRepository
from app.schemas import AnswerContext, ChatRequest, Source


@unittest.skipUnless(os.getenv('RUN_OLLAMA_TESTS') == '1', 'Postman Ollama 시뮬레이션 실행 시 활성화')
class OllamaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = asyncio.Runner()

    @classmethod
    def tearDownClass(cls):
        cls.runner.close()

    def client(self):
        client = OllamaClient()
        client.model = 'contract-test-model'
        return client

    def setUp(self):
        item = patch('app.tools.execution.RagService.search', AsyncMock(return_value=[Source(document='fixture.pdf',text='규정')]))
        item.start(); self.addCleanup(item.stop)
        item = patch('app.tools.execution.business_data', return_value=({}, None))
        item.start(); self.addCleanup(item.stop)

    def test_database_history_is_sent_to_model_once_in_order(self):
        if settings.storage_backend == 'mysql':
            self.assertTrue(settings.mysql_database.endswith('_test'))
            repository = MySQLConversationRepository()
        else:
            repository = MemoryConversationRepository()
        service = ChatService(repository, tools=LocalToolGateway())
        service.ollama = self.client()
        employee_id = f'OLLAMA-{uuid4().hex[:12]}'
        if settings.storage_backend == 'mysql':
            with connection_scope() as connection, connection.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO employees (employee_id, name, department, job_title, created_at) VALUES (%s, %s, %s, %s, UTC_TIMESTAMP(6))',
                    (employee_id, '모의 사용자', '연구팀', '사원'),
                )
        else:
            import json
            import tempfile
            from pathlib import Path
            from app.repositories.users import FileUserRepository
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            path = Path(temporary.name) / 'users.json'
            path.write_text(json.dumps([{'employee_id': employee_id, 'name': '모의 사용자', 'department': '연구팀'}]), encoding='utf-8')
            service.users = FileUserRepository(path)
        conversation = repository.create(employee_id)
        other = repository.create(employee_id)
        with patch('app.agent.service.settings', replace(settings, answer_provider='ollama')):
            self.runner.run(service.reply(other, ChatRequest(message='다른 세션 기록')))
            for index in range(7):
                self.runner.run(service.reply(conversation, ChatRequest(message=f'기록 {index}')))
            response = self.runner.run(service.reply(conversation, ChatRequest(message='마지막 질문')))
        with httpx.Client(trust_env=False) as client:
            sent = client.get(f'{service.ollama.base_url}/__test/last-request').json()
        self.assertFalse(sent['stream'])
        self.assertEqual(sent['messages'][0]['role'], 'system')
        self.assertEqual(len(sent['messages']), 12)  # system + 이전 10개 + 현재 질문 1개
        previous = sent['messages'][1:-1]
        self.assertEqual(previous, response.context.history)
        self.assertEqual([item['content'] for item in previous if item['role'] == 'user'], [f'기록 {index}' for index in range(2, 7)])
        self.assertNotIn('다른 세션 기록', str(sent))
        self.assertEqual(sent['messages'][-1]['content'].count('마지막 질문'), 1)
        import json
        evidence = json.loads(sent['messages'][-1]['content'].split('## 사용자 정보\n```json\n')[1].split('\n```')[0])
        self.assertEqual(evidence['user_profile']['employee_id'], employee_id)
        self.assertEqual(evidence['user_profile']['department'], '연구팀')
        self.assertEqual(evidence['user_profile_status'], 'found')
        self.assertEqual(repository.get(conversation.id).messages[-1].content, response.answer)
        self.assertEqual(len(repository.get(conversation.id).messages), 16)

    def test_errors_and_timeout_do_not_return_fake_answers(self):
        client = self.client()
        for question in ('__simulate_failure__', '__simulate_malformed__', '__simulate_delay__'):
            with self.subTest(question=question), patch('app.integrations.ollama.settings', replace(settings, ollama_timeout=0.1)):
                with self.assertRaises(ModelUnavailable):
                    self.runner.run(client.generate_answer(AnswerContext(question=question, employee_id='TEST', sources=[Source(document='fixture.pdf', text='규정')])))

    def test_model_failure_does_not_save_half_a_turn(self):
        repository = MemoryConversationRepository()
        conversation = repository.create('TEST')
        service = ChatService(repository, tools=LocalToolGateway())
        service.ollama = self.client()
        with patch('app.agent.service.settings', replace(settings, answer_provider='ollama')):
            with self.assertRaises(ModelUnavailable):
                self.runner.run(service.reply(conversation, ChatRequest(message='__simulate_failure__')))
        self.assertEqual(repository.get(conversation.id).messages, [])


if __name__ == '__main__':
    unittest.main()
