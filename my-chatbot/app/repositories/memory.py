from datetime import datetime, timezone
from threading import RLock
from uuid import UUID, uuid4

from app.errors import ConversationConflict
from app.integrations.n8n import compact_end_payload
from app.schemas import AnswerContext, Conversation, EndResponse, Message


class MemoryConversationRepository:
    """DB 설정 전 명시적으로 선택하는 데모용 저장소."""

    storage_name = "memory"

    def __init__(self):
        self._items: dict[UUID, Conversation] = {}
        self._lock = RLock()
        self._events: dict[UUID, dict] = {}

    def create(self, employee_id: str) -> Conversation:
        conversation = Conversation(
            id=uuid4(), employee_id=employee_id, created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._items[conversation.id] = conversation
        return conversation.model_copy(deep=True)

    def get(self, conversation_id: UUID, *, include_messages: bool = True) -> Conversation | None:
        with self._lock:
            item = self._items.get(conversation_id)
            if item is None:
                return None
            copy = item.model_copy(deep=True)
            if not include_messages:
                copy.messages = []
            return copy

    def recent_messages(self, conversation_id: UUID, limit: int) -> list[Message]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._items[conversation_id].messages[-limit:]]

    def user_messages(self, conversation_id: UUID, limit: int = 30) -> list[Message]:
        with self._lock:
            items = [item for item in self._items[conversation_id].messages if item.role == 'user']
            return [item.model_copy(deep=True) for item in items[-min(max(limit, 1), 30):]]

    def append_turn(self, conversation_id: UUID, messages: list[Message],
                    context: AnswerContext, expected_last_id: UUID | None) -> None:
        with self._lock:
            conversation = self._items[conversation_id]
            last_id = conversation.messages[-1].id if conversation.messages else None
            if conversation.status != "open" or last_id != expected_last_id:
                raise ConversationConflict("대화가 종료되었거나 다른 질문이 먼저 처리되었습니다. 대화를 확인하고 다시 시도해주세요.")
            conversation.messages.extend(item.model_copy(deep=True) for item in messages)

    def close(self, conversation_id: UUID, result: EndResponse, payload: dict) -> EndResponse:
        with self._lock:
            conversation = self._items[conversation_id]
            if conversation.end_result is not None:
                from app.integrations.n8n import has_feedback
                if has_feedback(conversation.end_result) or not has_feedback(result):
                    return conversation.end_result.model_copy(deep=True)
                payload['previous_event_id']=str(conversation.end_result.event_id)
            conversation.status = "closed"
            conversation.end_result = result.model_copy(deep=True)
            self._events[conversation_id] = {'status':result.webhook_status, 'payload':compact_end_payload(
                payload, [m.model_dump(mode='json') for m in conversation.messages])}
            return result

    def claim_webhook(self, conversation_id: UUID) -> dict | None:
        with self._lock:
            item = self._events.get(conversation_id)
            if item is None or item['status'] not in {'pending', 'failed', 'not_configured'}:
                return None
            item['status'] = 'sending'
            return item['payload'].copy()

    def finish_webhook(self, conversation_id: UUID, status: str, error: str | None) -> EndResponse:
        with self._lock:
            self._events[conversation_id]['status'] = status
            result = self._items[conversation_id].end_result
            result.webhook_status = status
            result.webhook_error = error
            result.message = {'sent':'대화가 종료되었습니다. 이용해 주셔서 감사합니다.', 'failed':'평가는 저장했지만 n8n 전송에 실패했습니다. 다시 전송할 수 있습니다.'}.get(status, '대화가 종료되었습니다. 이용해 주셔서 감사합니다.')
            return result.model_copy(deep=True)

    def ping(self) -> None:
        return None

    def search_inquiries(self,employee_id: str,keyword: str,limit: int) -> list[dict]:
        from app.repositories.inquiry_records import matching_record
        output=[]
        with self._lock:
            for conversation in self._items.values():
                if conversation.employee_id!=employee_id:
                    continue
                for q,a in zip(conversation.messages,conversation.messages[1:]):
                    if q.role!='user' or a.role!='assistant':
                        continue
                    record=dict(inquiry_id=str(q.id),employee_id=employee_id,question=q.content,answer=a.content,
                                category=', '.join(a.tools_used),created_at=q.created_at.isoformat(),status='recorded')
                    if matching_record(record,keyword):
                        output.append(record)
        return sorted(output,key=lambda item:item['created_at'],reverse=True)[:min(max(limit,1),100)]
