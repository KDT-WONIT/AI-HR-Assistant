import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.errors import ConversationConflict
from app.integrations.mysql import connection_scope
from app.integrations.n8n import compact_end_payload
from app.schemas import AnswerContext, Conversation, EndResponse, Message


def utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def decode(value, default):
    if value is None:
        return default
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def read_message(row: dict) -> Message:
    return Message(
        id=row["id"], role=row["role"], content=row["content"],
        created_at=row["created_at"].replace(tzinfo=timezone.utc),
        sources=decode(row["sources"], []), tools_used=decode(row["tools_used"], []),
        contact_escalation=decode(row.get('context_data'),{}).get('contact_escalation',{}),
    )


class MySQLConversationRepository:
    storage_name = "mysql"

    def search_inquiries(self,employee_id: str,keyword: str,limit: int) -> list[dict]:
        from app.repositories.inquiry_records import INQUIRY_SELECT,inquiry_record
        with connection_scope() as connection,connection.cursor(dictionary=True) as cursor:
            cursor.execute(INQUIRY_SELECT.format(parameter='%s'),
                           (employee_id,keyword,keyword,keyword,keyword,min(max(limit,1),100)))
            rows=cursor.fetchall()
        return [inquiry_record(row) for row in rows]

    def create(self, employee_id: str) -> Conversation:
        conversation = Conversation(id=uuid4(), employee_id=employee_id, created_at=datetime.now(timezone.utc))
        with connection_scope() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO conversations (id, employee_id, status, created_at) VALUES (%s, %s, %s, %s)",
                (str(conversation.id), employee_id, "open", utc_naive(conversation.created_at)),
            )
        return conversation

    def get(self, conversation_id: UUID, *, include_messages: bool = True) -> Conversation | None:
        with connection_scope() as connection, connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM conversations WHERE id = %s", (str(conversation_id),))
            row = cursor.fetchone()
            if row is None:
                return None
            messages = []
            if include_messages:
                cursor.execute("SELECT * FROM messages WHERE conversation_id = %s ORDER BY sequence_id", (str(conversation_id),))
                messages = [read_message(message) for message in cursor.fetchall()]
            return Conversation(
                id=row["id"], employee_id=row["employee_id"], status=row["status"],
                created_at=row["created_at"].replace(tzinfo=timezone.utc),
                messages=messages, end_result=decode(row["end_result"], None),
            )

    def recent_messages(self, conversation_id: UUID, limit: int) -> list[Message]:
        if not 1 <= limit <= 10:
            raise ValueError("최근 메시지는 1~10개만 조회할 수 있습니다.")
        with connection_scope() as connection, connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM messages WHERE conversation_id = %s ORDER BY sequence_id DESC LIMIT %s",
                (str(conversation_id), limit),
            )
            return [read_message(row) for row in reversed(cursor.fetchall())]

    def append_turn(self, conversation_id: UUID, messages: list[Message],
                    context: AnswerContext, expected_last_id: UUID | None) -> None:
        with connection_scope() as connection, connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT status FROM conversations WHERE id = %s FOR UPDATE", (str(conversation_id),))
            row = cursor.fetchone()
            if row is None or row["status"] != "open":
                raise ConversationConflict("종료되었거나 존재하지 않는 대화입니다.")
            cursor.execute("SELECT id FROM messages WHERE conversation_id = %s ORDER BY sequence_id DESC LIMIT 1", (str(conversation_id),))
            last = cursor.fetchone()
            last_id = UUID(last["id"]) if last else None
            if last_id != expected_last_id:
                raise ConversationConflict("다른 질문이 먼저 처리되었습니다. 대화를 확인하고 다시 시도해주세요.")
            for message in messages:
                cursor.execute(
                    "INSERT INTO messages (id, conversation_id, role, content, sources, tools_used, context_data, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (str(message.id), str(conversation_id), message.role, message.content,
                     json.dumps([source.model_dump(mode="json") for source in message.sources], ensure_ascii=False),
                     json.dumps(message.tools_used, ensure_ascii=False),
                     context.model_dump_json() if message.role == "assistant" else None,
                     utc_naive(message.created_at)),
                )

    def close(self, conversation_id: UUID, result: EndResponse, payload: dict) -> EndResponse:
        with connection_scope() as connection, connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT status, end_result FROM conversations WHERE id = %s FOR UPDATE", (str(conversation_id),))
            row = cursor.fetchone()
            if row is None:
                raise ConversationConflict("존재하지 않는 대화입니다.")
            if row["status"] == "closed":
                if row["end_result"] is None:
                    raise ConversationConflict("기존 대화가 이미 종료되었습니다.")
                return EndResponse.model_validate(decode(row["end_result"], None))
            cursor.execute("SELECT * FROM messages WHERE conversation_id = %s ORDER BY sequence_id", (str(conversation_id),))
            payload = compact_end_payload(payload, [read_message(item).model_dump(mode="json") for item in cursor.fetchall()])
            cursor.execute(
                "UPDATE conversations SET status = 'closed', ended_at = %s, end_result = %s WHERE id = %s",
                (utc_naive(result.ended_at), result.model_dump_json(), str(conversation_id)),
            )
            cursor.execute(
                "INSERT INTO feedback (conversation_id, rating, comment, created_at) VALUES (%s, %s, %s, %s)",
                (str(conversation_id), result.rating, result.comment, utc_naive(result.ended_at)),
            )
            cursor.execute(
                "INSERT INTO webhook_events (event_id, conversation_id, event_type, payload, status, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (str(result.event_id), str(conversation_id), payload.get('event','session_end'),
                 json.dumps(payload, ensure_ascii=False), result.webhook_status, utc_naive(result.ended_at)),
            )
            return result

    def claim_webhook(self, conversation_id: UUID) -> dict | None:
        with connection_scope() as connection, connection.cursor(dictionary=True) as cursor:
            cursor.execute('SELECT event_id,payload,status FROM webhook_events WHERE conversation_id=%s FOR UPDATE', (str(conversation_id),))
            row = cursor.fetchone()
            if row is None or row['status'] not in {'pending','failed','not_configured'}:
                return None
            cursor.execute("UPDATE webhook_events SET status='sending',attempts=attempts+1 WHERE event_id=%s", (row['event_id'],))
            return decode(row['payload'], {})

    def finish_webhook(self, conversation_id: UUID, status: str, error: str | None) -> EndResponse:
        with connection_scope() as connection, connection.cursor(dictionary=True) as cursor:
            cursor.execute('SELECT end_result FROM conversations WHERE id=%s FOR UPDATE', (str(conversation_id),))
            result = EndResponse.model_validate(decode(cursor.fetchone()['end_result'], None))
            result.webhook_status = status
            result.message = {'sent':'대화와 평가를 저장하고 n8n에 전송했습니다.',
                              'failed':'대화와 평가는 저장했지만 n8n 전송에 실패했습니다. 다시 전송할 수 있습니다.'}.get(status, '대화를 종료했습니다.')
            cursor.execute('UPDATE webhook_events SET status=%s,last_error=%s,sent_at=%s WHERE conversation_id=%s',
                           (status,error,utc_naive(datetime.now(timezone.utc)) if status=='sent' else None,str(conversation_id)))
            cursor.execute('UPDATE conversations SET end_result=%s WHERE id=%s', (result.model_dump_json(),str(conversation_id)))
            return result

    def ping(self) -> None:
        with connection_scope() as connection, connection.cursor() as cursor:
            for query in (
                "SELECT end_result FROM conversations LIMIT 0",
                "SELECT sequence_id FROM messages LIMIT 0",
                "SELECT event_id FROM webhook_events LIMIT 0",
                "SELECT rating FROM feedback LIMIT 0",
            ):
                cursor.execute(query)
                cursor.fetchall()
