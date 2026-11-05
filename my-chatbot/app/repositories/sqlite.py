import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.errors import ConversationConflict
from app.integrations.sqlite import connection_scope
from app.integrations.n8n import compact_end_payload
from app.schemas import AnswerContext, Conversation, EndResponse, Message


def read_message(row) -> Message:
    context = json.loads(row['context_data'] or '{}')
    return Message(id=row['id'], role=row['role'], content=row['content'], created_at=row['created_at'],
                   sources=json.loads(row['sources'] or '[]'), tools_used=json.loads(row['tools_used'] or '[]'),
                   contact_escalation=context.get('contact_escalation',{}),processing_status=context.get('processing_status','answered'))


class SQLiteConversationRepository:
    storage_name = 'sqlite'

    def create(self, employee_id: str) -> Conversation:
        item = Conversation(id=uuid4(), employee_id=employee_id, created_at=datetime.now(timezone.utc))
        with connection_scope(write=True) as connection:
            connection.execute('INSERT INTO conversations(id,employee_id,status,created_at) VALUES(?,?,?,?)',
                               (str(item.id), employee_id, 'open', item.created_at.isoformat()))
        return item

    def get(self, conversation_id: UUID, *, include_messages: bool = True) -> Conversation | None:
        with connection_scope() as connection:
            row = connection.execute('SELECT * FROM conversations WHERE id=?', (str(conversation_id),)).fetchone()
            if row is None:
                return None
            messages = [read_message(item) for item in connection.execute(
                'SELECT * FROM messages WHERE conversation_id=? ORDER BY sequence_id', (str(conversation_id),)
            )] if include_messages else []
            return Conversation(id=row['id'], employee_id=row['employee_id'], status=row['status'],
                                created_at=row['created_at'], messages=messages,
                                end_result=json.loads(row['end_result']) if row['end_result'] else None)

    def recent_messages(self, conversation_id: UUID, limit: int) -> list[Message]:
        if not 1 <= limit <= 10:
            raise ValueError('최근 메시지 수는 1~10이어야 합니다.')
        with connection_scope() as connection:
            rows = connection.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY sequence_id DESC LIMIT ?',
                                      (str(conversation_id), limit)).fetchall()
            return [read_message(row) for row in reversed(rows)]

    def user_messages(self, conversation_id: UUID, limit: int = 30) -> list[Message]:
        with connection_scope() as connection:
            rows = connection.execute(
                "SELECT * FROM messages WHERE conversation_id=? AND role='user' ORDER BY sequence_id DESC LIMIT ?",
                (str(conversation_id), min(max(limit, 1), 30)),
            ).fetchall()
            return [read_message(row) for row in reversed(rows)]

    def append_turn(self, conversation_id: UUID, messages: list[Message], context: AnswerContext,
                    expected_last_id: UUID | None) -> None:
        with connection_scope(write=True) as connection:
            row = connection.execute('SELECT status FROM conversations WHERE id=?', (str(conversation_id),)).fetchone()
            last = connection.execute('SELECT id FROM messages WHERE conversation_id=? ORDER BY sequence_id DESC LIMIT 1',
                                      (str(conversation_id),)).fetchone()
            if row is None or row['status'] != 'open' or (UUID(last['id']) if last else None) != expected_last_id:
                raise ConversationConflict('대화가 종료되었거나 다른 질문이 먼저 처리되었습니다. 다시 시도해주세요.')
            for message in messages:
                connection.execute(
                    'INSERT INTO messages(id,conversation_id,role,content,sources,tools_used,context_data,created_at) VALUES(?,?,?,?,?,?,?,?)',
                    (str(message.id), str(conversation_id), message.role, message.content,
                     json.dumps([item.model_dump(mode='json') for item in message.sources], ensure_ascii=False),
                     json.dumps(message.tools_used), context.model_dump_json() if message.role == 'assistant' else None,
                     message.created_at.isoformat()),
                )

    def close(self, conversation_id: UUID, result: EndResponse, payload: dict) -> EndResponse:
        with connection_scope(write=True) as connection:
            row = connection.execute('SELECT status,end_result FROM conversations WHERE id=?', (str(conversation_id),)).fetchone()
            if row is None:
                raise ConversationConflict('대화를 찾을 수 없습니다.')
            if row['status'] == 'closed':
                from app.integrations.n8n import has_feedback
                previous=EndResponse.model_validate_json(row['end_result'])
                if has_feedback(previous) or not has_feedback(result):
                    return previous
                payload['previous_event_id']=str(previous.event_id)
            payload = compact_end_payload(payload, [read_message(item).model_dump(mode='json') for item in connection.execute(
                'SELECT * FROM messages WHERE conversation_id=? ORDER BY sequence_id', (str(conversation_id),)
            )])
            connection.execute('UPDATE conversations SET status=?,ended_at=?,end_result=? WHERE id=?',
                               ('closed', result.ended_at.isoformat(), result.model_dump_json(), str(conversation_id)))
            connection.execute('INSERT INTO feedback(conversation_id,rating,comment,created_at) VALUES(?,?,?,?) '
                               'ON CONFLICT(conversation_id) DO UPDATE SET rating=excluded.rating,comment=excluded.comment',
                               (str(conversation_id), result.rating, result.comment, result.ended_at.isoformat()))
            connection.execute('INSERT INTO webhook_events(event_id,conversation_id,event_type,payload,status,created_at) VALUES(?,?,?,?,?,?) '
                               'ON CONFLICT(conversation_id) DO UPDATE SET event_id=excluded.event_id,event_type=excluded.event_type,'
                               'payload=excluded.payload,status=excluded.status,attempts=0,last_error=NULL,sent_at=NULL',
                               (str(result.event_id), str(conversation_id), payload.get('event','session_end'), json.dumps(payload, ensure_ascii=False),
                                result.webhook_status, result.ended_at.isoformat()))
        return result

    def claim_webhook(self, conversation_id: UUID) -> dict | None:
        with connection_scope(write=True) as connection:
            row = connection.execute('SELECT event_id,payload,status FROM webhook_events WHERE conversation_id=?',
                                     (str(conversation_id),)).fetchone()
            if row is None or row['status'] not in {'pending', 'failed', 'not_configured'}:
                return None
            connection.execute("UPDATE webhook_events SET status='sending',attempts=attempts+1 WHERE event_id=?", (row['event_id'],))
            return json.loads(row['payload'])

    def finish_webhook(self, conversation_id: UUID, status: str, error: str | None) -> EndResponse:
        with connection_scope(write=True) as connection:
            row = connection.execute('SELECT end_result FROM conversations WHERE id=?', (str(conversation_id),)).fetchone()
            result = EndResponse.model_validate_json(row['end_result'])
            result.webhook_status = status
            result.webhook_error = error
            result.message = {'sent':'대화가 종료되었습니다. 이용해 주셔서 감사합니다.',
                              'failed':'대화와 평가는 저장했지만 n8n 전송에 실패했습니다. 다시 전송할 수 있습니다.',
                              'not_configured':'대화와 평가는 저장했습니다. n8n 주소는 아직 설정되지 않았습니다.'}.get(status, '대화가 종료되었습니다. 이용해 주셔서 감사합니다.')
            if error=='receiver_unconfirmed':
                result.message='평가는 로컬에 저장했습니다. n8n이 평가 처리 확인(ok:true)을 반환하지 않아 시트 저장 여부를 확인할 수 없습니다.'
            elif error=='receiver_no_update':
                result.message='평가는 로컬에 저장했습니다. n8n이 시트 갱신 실패를 반환했습니다. 종료 이벤트의 분기와 session_id 매핑을 확인해주세요.'
            connection.execute('UPDATE webhook_events SET status=?,last_error=?,sent_at=? WHERE conversation_id=?',
                               (status,error,datetime.now(timezone.utc).isoformat() if status=='sent' else None,str(conversation_id)))
            connection.execute('UPDATE conversations SET end_result=? WHERE id=?', (result.model_dump_json(),str(conversation_id)))
            return result

    def ping(self) -> None:
        with connection_scope() as connection:
            connection.execute('SELECT id FROM conversations LIMIT 0')

    def search_inquiries(self,employee_id: str,keyword: str,limit: int) -> list[dict]:
        from app.repositories.inquiry_records import INQUIRY_SELECT,inquiry_record
        with connection_scope() as connection:
            rows=connection.execute(INQUIRY_SELECT.format(parameter='?'),
                                    (employee_id,keyword,keyword,keyword,keyword,min(max(limit,1),100))).fetchall()
        return [inquiry_record(row) for row in rows]
