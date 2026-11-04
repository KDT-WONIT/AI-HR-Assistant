"""RUN_MYSQL_TESTS=1 + 이름이 _test로 끝나는 전용 DB에서만 실행합니다."""

import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.config import settings
from app.errors import ConversationConflict, StorageUnavailable
from app.integrations.mysql import connection_scope
from app.repositories.mysql import MySQLConversationRepository
from app.repositories.users import MySQLUserRepository
from app.schemas import AnswerContext, EndResponse, Message


@unittest.skipUnless(os.getenv('RUN_MYSQL_TESTS') == '1', '전용 MySQL 테스트 DB 설정 시 실행')
class MySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not settings.mysql_database.endswith('_test'):
            raise RuntimeError('MySQL 테스트는 이름이 _test로 끝나는 전용 DB에서만 실행하세요.')
        cls.repository = MySQLConversationRepository()
        cls.repository.ping()

    def pair(self, question):
        now = datetime.now(timezone.utc)
        return [Message(id=uuid4(), role='user', content=question, created_at=now),
                Message(id=uuid4(), role='assistant', content=f'답변: {question} 😊', created_at=now)]

    def test_user_import_lookup_refresh_and_context(self):
        import json
        import tempfile
        from pathlib import Path
        from scripts.import_users import import_profiles
        user_id = f'PROFILE-{uuid4().hex[:12]}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'users.json'
            profile = {'employee_id': user_id, 'name': '가상 직원', 'department': '개발팀', 'job_title': '사원', 'hired_at': '2025-01-02'}
            path.write_text(json.dumps([profile]), encoding='utf-8')
            self.assertEqual(import_profiles(path), 1)
            users = MySQLUserRepository()
            self.assertEqual(users.get(user_id).department, '개발팀')
            self.assertEqual(users.get(user_id).hired_at.isoformat(), '2025-01-02')
            self.assertIsNone(users.get('NONEXISTENT-' + uuid4().hex))
            profile['department'] = '연구팀'
            path.write_text(json.dumps([profile]), encoding='utf-8')
            self.assertEqual(import_profiles(path), 1)
            self.assertEqual(MySQLUserRepository().get(user_id).department, '연구팀')
            context = AnswerContext(question='사용자 질문', employee_id=user_id, user_profile=users.get(user_id), user_profile_status='found')
            conversation = self.repository.create(user_id)
            self.repository.append_turn(conversation.id, self.pair('사용자 질문'), context, None)
            with connection_scope() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT context_data FROM messages WHERE conversation_id = %s AND role = 'assistant'", (str(conversation.id),))
                stored = json.loads(cursor.fetchone()[0])
                self.assertEqual(stored['user_profile']['department'], '연구팀')

    def test_persistence_recent_limit_and_session_isolation(self):
        first = self.repository.create('MYSQL-TEST')
        other = self.repository.create('MYSQL-TEST')
        context = AnswerContext(question='test', employee_id='MYSQL-TEST')
        self.repository.append_turn(other.id, self.pair('다른 세션'), context, None)
        last_id = None
        for index in range(8):
            messages = self.pair(f'질문 {index}')
            self.repository.append_turn(first.id, messages, context, last_id)
            last_id = messages[-1].id
        fresh = MySQLConversationRepository()
        self.assertEqual(len(fresh.get(first.id).messages), 16)
        self.assertEqual(fresh.get(first.id, include_messages=False).messages, [])
        recent = fresh.recent_messages(first.id, 10)
        self.assertEqual(len(recent), 10)
        self.assertEqual([item.content for item in recent if item.role == 'user'], [f'질문 {index}' for index in range(3, 8)])
        self.assertTrue(all('다른 세션' not in item.content for item in recent))
        self.assertEqual([item.content for item in fresh.recent_messages(first.id, 5)], [item.content for item in recent[-5:]])
        self.assertTrue(all(item.created_at.tzinfo is not None for item in recent))

    def test_rollback_and_stale_context(self):
        conversation = self.repository.create('MYSQL-TEST')
        context = AnswerContext(question='test', employee_id='MYSQL-TEST')
        original = self.pair('처음')
        self.repository.append_turn(conversation.id, original, context, None)
        bad = self.pair('롤백되어야 함')
        bad[-1].id = original[-1].id
        with self.assertRaises(StorageUnavailable):
            self.repository.append_turn(conversation.id, bad, context, original[-1].id)
        self.assertEqual(len(self.repository.get(conversation.id).messages), 2)
        with self.assertRaises(ConversationConflict):
            self.repository.append_turn(conversation.id, self.pair('오래된 컨텍스트'), context, None)
        self.assertEqual(len(self.repository.get(conversation.id).messages), 2)

    def test_close_feedback_event_and_reconnect(self):
        conversation = self.repository.create('MYSQL-TEST')
        context = AnswerContext(question='test', employee_id='MYSQL-TEST')
        messages = self.pair('종료 테스트')
        self.repository.append_turn(conversation.id, messages, context, None)
        result = EndResponse(conversation_id=conversation.id, ended_at=datetime.now(timezone.utc),
                             rating='helpful', comment='확인', event_id=uuid4(),
                             webhook_status='not_configured', message='저장됨')
        payload = {'event': 'conversation.ended', 'event_id': str(result.event_id)}
        self.repository.close(conversation.id, result, payload)
        changed = result.model_copy(update={'rating': 'unhelpful', 'event_id': uuid4()})
        repeated = MySQLConversationRepository().close(conversation.id, changed, payload)
        self.assertEqual(repeated, result)
        self.assertEqual(MySQLConversationRepository().get(conversation.id).end_result, result)
        with connection_scope() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM feedback WHERE conversation_id = %s', (str(conversation.id),))
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute('SELECT payload FROM webhook_events WHERE conversation_id = %s', (str(conversation.id),))
            import json
            self.assertEqual(len(json.loads(cursor.fetchone()[0])['messages']), 2)
        with self.assertRaises(ConversationConflict):
            self.repository.append_turn(conversation.id, self.pair('종료 후 질문'), context, messages[-1].id)


if __name__ == '__main__':
    unittest.main()
