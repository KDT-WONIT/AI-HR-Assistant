from datetime import datetime, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL

from starlette.concurrency import run_in_threadpool

from app.agent.context import build_context
from app.agent.router import select_tools
from app.agent.escalation import ContactRecommender
from app.config import settings
from app.integrations.n8n import N8nClient, log_delivery
from app.integrations.ollama import OllamaClient
from app.mcp.client import ToolGateway, tool_gateway
from app.repositories.base import ConversationRepository
from app.repositories.users import UserRepository, create_user_repository
from app.schemas import (
    ChatRequest, ChatResponse, Conversation, EndRequest, EndResponse, Message, Step, ToolInput, WebhookDelivery,
)


class ChatService:
    def __init__(self, repository: ConversationRepository, users: UserRepository | None = None,
                 tools: ToolGateway | None = None):
        self.repository = repository
        self.users = users if users is not None else create_user_repository(repository.storage_name)
        self.n8n = N8nClient()
        self.ollama = OllamaClient()
        self.tools = tools if tools is not None else tool_gateway
        self.contacts = ContactRecommender()

    async def start_conversation(self, employee_id: str) -> Conversation:
        conversation = await run_in_threadpool(self.repository.create,employee_id)
        profile = await run_in_threadpool(self.users.get,employee_id)
        payload = self.event_payload(conversation,settings.n8n_event_session_start,
                                     event_id=uuid5(NAMESPACE_URL,f'hr:{conversation.id}:session_start'),
                                     started_at=conversation.created_at.isoformat(),session_status='OPEN',
                                     user=self.basic_user(profile,employee_id))
        conversation.webhook_events = [await self.send_log(payload)]
        return conversation

    @staticmethod
    def basic_user(profile, employee_id):
        return ({key:value for key,value in profile.model_dump(mode='json').items()
                 if key in {'employee_id','name','department','job_title'}} if profile else {'employee_id':employee_id})

    @staticmethod
    def event_payload(conversation, event, *, event_id=None, **fields):
        return {'event':event,'event_id':str(event_id or uuid4()),'session_id':str(conversation.id),
                'conversation_id':str(conversation.id),'employee_id':conversation.employee_id,
                'occurred_at':datetime.now(timezone.utc).isoformat(),**fields}

    async def send_log(self, payload) -> WebhookDelivery:
        # 기록 서버의 장애로 대화를 중단하지 않으며 전송 결과도 호출자에게 반환합니다.
        if settings.n8n_webhook_url:
            delivery = await self.n8n.send_event(payload)
        else:
            from app.integrations.n8n import DeliveryResult
            delivery = DeliveryResult('not_configured')
        log_delivery(payload,delivery)
        return WebhookDelivery(event=payload['event'],event_id=payload['event_id'],status=delivery.status,error=delivery.error)

    async def reply(self, conversation: Conversation, data: ChatRequest) -> ChatResponse:
        question_id = uuid4()
        question_at = datetime.now(timezone.utc)
        question_payload = self.event_payload(conversation,settings.n8n_event_question,
            message_id=str(question_id),question=data.message,asked_at=question_at.isoformat(),answer_status='PENDING')
        deliveries = [*conversation.webhook_events,await self.send_log(question_payload)]
        try:
            response = await self._reply(conversation,data,question_id,question_at)
        except Exception:
            # 질문이 PENDING에 남지 않도록 생성 실패도 같은 message_id로 알립니다.
            await self.send_log(self.event_payload(conversation,settings.n8n_event_answer,
                message_id=str(question_id),question=data.message,answer='',answer_status='FAILED',
                error_code='chat_processing_failed',answered_at=datetime.now(timezone.utc).isoformat()))
            raise
        deliveries.append(await self.send_log(self.event_payload(conversation,settings.n8n_event_answer,
            message_id=str(question_id),answer_message_id=str(response.message_id),question=data.message,
            answer=response.answer,answer_status='ANSWERED',processing_status=response.status,
            category=response.tools_used[0] if response.tools_used else None,tools_used=response.tools_used,
            answered_at=datetime.now(timezone.utc).isoformat())))
        response.webhook_events = deliveries
        return response

    async def _reply(self, conversation: Conversation, data: ChatRequest, question_id, question_at) -> ChatResponse:
        profile = await run_in_threadpool(self.users.get, conversation.employee_id)
        request = ToolInput(
            question=data.message, employee_id=conversation.employee_id,
            conversation_id=conversation.id,
            user_profile=profile,
        )
        history = await run_in_threadpool(
            self.repository.recent_messages, conversation.id, settings.history_message_limit,
        )
        catalog = await self.tools.list_tools()
        decision = await select_tools(request, data.tool_id, self.ollama,
                                      [{'role': item.role, 'content': item.content} for item in history], catalog)
        request.arguments = decision.arguments.model_dump()
        selected = [decision.tool_id]
        results = [await self.tools.execute(decision.tool_id, request)]
        context = build_context(request, history, results)
        names = [tool.name for tool in catalog if tool.id == decision.tool_id]
        result = results[0]
        people_lookup = not context.sources and any(result.data.get(key) for key in ('employee','hr_contacts','departments'))
        status = 'answered'
        generated = False
        if result.status == 'no_result':
            status = 'no_result'
            context.answer_coverage = 'missing'
            answer = '제공된 사내 규정에서 관련 근거를 찾지 못했습니다. 질문을 구체적으로 입력하거나 담당 부서에 확인해주세요.'
        elif result.status == 'needs_input':
            status = 'needs_input'
            context.answer_coverage = 'missing'
            answer = result.message
        elif settings.answer_provider == 'ollama':
            answer = await self.ollama.generate_answer(context)
            generated = bool(context.sources)  # 사원 조회 결과만 있으면 모델 호출 없이 사실을 정리합니다.
        else:
            import json
            excerpts = [f'[{index}] {source.document} p.{source.page or "?"}\n{source.text[:1200]}'
                        for index, source in enumerate(context.sources, 1)]
            answer = '검색/조회 결과 (답변 모델 미사용)\n\n' + '\n\n'.join(excerpts)
            if result.data:
                answer += '\n\n업무 조회/계산:\n' + json.dumps(result.data, ensure_ascii=False, indent=2)
        if context.answer_coverage == 'unknown':
            context.answer_coverage = 'direct'
        needs_contact = context.answer_coverage in {'partial','missing'}
        if needs_contact:
            context.contact_escalation = await run_in_threadpool(
                self.contacts.recommend,data.message,conversation.employee_id,context.history,
            )
        if context.answer_coverage == 'missing' and status == 'answered':
            status = 'needs_review'
        assistant_id = uuid4()
        messages = [
            Message(id=question_id, role="user", content=data.message, created_at=question_at),
            Message(
                id=assistant_id, role="assistant", content=answer, created_at=datetime.now(timezone.utc),
                sources=context.sources, tools_used=selected,
                contact_escalation=context.contact_escalation,
            ),
        ]
        await run_in_threadpool(
            self.repository.append_turn, conversation.id, messages, context,
            history[-1].id if history else None,
        )
        return ChatResponse(
            conversation_id=conversation.id, message_id=assistant_id, answer=answer,
            sources=context.sources, tools_used=selected, tool_results=results, context=context,
            mode=settings.mode, answer_provider=settings.answer_provider,
            status=status,
            contact_escalation=context.contact_escalation,
            steps=[
                Step(key="receive", label="질문 접수", detail="FastAPI 요청 검증 완료", status="done"),
                Step(key="route", label="도구 선택", detail=names[0] + (' · 직접 지정' if data.tool_id else ' · Ollama 선택'), status="done"),
                Step(key="tools", label="도구 실행", detail=f'{self.tools.transport} · ' + ('사원·부서 조회' if people_lookup else f'문서 근거 {len(context.sources)}개') + f' · {result.status}', status="done"),
                Step(key="context", label="컨텍스트 구성", detail=f"사용자 정보 {'조회됨' if profile else '없음'} · 최근 메시지 {len(history)}개", status="done"),
                Step(key="generate", label="Ollama 답변 생성", detail="Ollama 응답 완료" if generated else '조회 결과/추가 정보 안내', status="done" if generated else "skipped"),
                *([Step(key='contacts',label='관련 담당자 조회',detail=f'업무 관련 문의 후보 {len(context.contact_escalation.contacts)}명',
                        status='done' if context.contact_escalation.contacts else 'skipped')] if needs_contact else []),
                Step(key="return", label="답변 출력", detail=f"{self.repository.storage_name}에 질문·답변 저장 완료", status="done"),
            ],
        )

    async def end(self, conversation: Conversation, data: EndRequest) -> EndResponse:
        if conversation.end_result is not None:
            return conversation.end_result
        profile = await run_in_threadpool(self.users.get, conversation.employee_id)
        ended_at = datetime.now(timezone.utc)
        event_id = uuid4()
        payload = {
            "event": settings.n8n_event_session_end, "event_id": str(event_id),
            "session_id": str(conversation.id), "session_status": "CLOSED",
            "occurred_at": ended_at.isoformat(),
            "conversation_id": str(conversation.id), "employee_id": conversation.employee_id,
            "ended_at": ended_at.isoformat(), "rating": data.rating, "comment": data.comment,
            "started_at": conversation.created_at.isoformat(),
            "user": ({key: value for key,value in profile.model_dump(mode='json').items()
                      if key in {'employee_id','name','department','job_title'}} if profile else
                     {'employee_id':conversation.employee_id}),
            "messages": [],  # 종료 트랜잭션에서 최근 대화의 요약용 데이터를 채웁니다.
        }
        webhook_status = 'pending' if settings.n8n_webhook_url else 'not_configured'
        result = EndResponse(
            conversation_id=conversation.id, ended_at=ended_at, rating=data.rating,
            comment=data.comment, event_id=event_id, webhook_status=webhook_status,
            message=('대화와 평가를 저장했습니다. n8n 전송을 준비합니다.' if settings.n8n_webhook_url else
                     '대화와 평가를 저장했습니다. n8n 주소는 아직 설정되지 않았습니다.'),
        )
        saved = await run_in_threadpool(self.repository.close, conversation.id, result, payload)
        if saved.event_id != event_id or not settings.n8n_webhook_url:
            return saved
        return await self.deliver_end_event(conversation.id)

    async def deliver_end_event(self, conversation_id) -> EndResponse:
        conversation = await run_in_threadpool(self.repository.get, conversation_id, include_messages=False)
        if conversation is None or conversation.end_result is None:
            from app.errors import ConversationConflict
            raise ConversationConflict('먼저 만족도를 제출하고 대화를 종료해주세요.')
        if not settings.n8n_webhook_url:
            return conversation.end_result.model_copy(update={'message':'n8n 주소가 비어 있습니다. .env 설정 후 서버를 다시 시작해주세요.'})
        payload = await run_in_threadpool(self.repository.claim_webhook, conversation_id)
        if payload is None:
            return conversation.end_result
        delivery = await self.n8n.send_conversation_ended(payload)
        log_delivery(payload,delivery)
        return await run_in_threadpool(self.repository.finish_webhook, conversation_id, delivery.status, delivery.error)
