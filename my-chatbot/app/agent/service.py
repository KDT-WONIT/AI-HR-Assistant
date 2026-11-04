import asyncio
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL

from starlette.concurrency import run_in_threadpool

from app.agent.context import build_context
from app.agent.emphasis import emphasize, strip_emphasis
from app.agent.general import GENERAL_TOOL_ID, GENERAL_TOOL_NAME
from app.agent.router import select_tools
from app.agent.escalation import ContactHints, ContactRecommender
from app.config import settings
from app import timing
from app.integrations.n8n import HANDLER_BLANK, N8nClient, answer_sheet_fields, log_delivery, satisfaction_fields, sheet_time
from app.integrations.ollama import OllamaClient
from app.mcp.client import ToolGateway, tool_gateway
from app.repositories.base import ConversationRepository
from app.repositories.users import UserRepository, create_user_repository
from app.schemas import (
    ChatRequest, ChatResponse, Conversation, EndRequest, EndResponse, Message, Step, ToolInput, WebhookDelivery,
)


TIMING_ORDER = ['도구 선택(툴콜링)', '임베딩', '벡터 검색', '표 복원', '도구 실행(그 외)', '답변 생성', '담당자 조회', 'n8n 호출']


class ChatService:
    def __init__(self, repository: ConversationRepository, users: UserRepository | None = None,
                 tools: ToolGateway | None = None):
        self.repository = repository
        self.users = users if users is not None else create_user_repository(repository.storage_name)
        self.n8n = N8nClient()
        self.ollama = OllamaClient()
        self.tools = tools if tools is not None else tool_gateway
        self.contacts = ContactRecommender()
        self._chains: dict[str, asyncio.Task] = {}  # 대화별 마지막 전송 작업(순서 보장)
        self._pending: set[asyncio.Task] = set()

    async def start_conversation(self, employee_id: str) -> Conversation:
        conversation = await run_in_threadpool(self.repository.create,employee_id)
        profile = await run_in_threadpool(self.users.get,employee_id)
        payload = self.event_payload(conversation,settings.n8n_event_session_start,
                                     event_id=uuid5(NAMESPACE_URL,f'hr:{conversation.id}:session_start'),
                                     started_at=sheet_time(conversation.created_at),ended_at='',session_status='OPEN',
                                     satisfaction_score=None,satisfaction_comment='',
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
                'occurred_at':sheet_time(),**fields}

    def enqueue(self, payload) -> None:
        """답변을 기다리게 하지 않도록 백그라운드로 전송합니다. 같은 대화의 이벤트는 보낸 순서대로 전송합니다."""
        key = payload['session_id']
        previous = self._chains.get(key)

        async def deliver():
            if previous is not None:
                await asyncio.wait({previous})
            try:
                began = time.monotonic()
                result = await self.n8n.send_event(payload)
                logging.getLogger('uvicorn.error').info('  └ n8n 호출(%s) %6.1f초 · %s%s%s', payload.get('event'),
                                                      time.monotonic() - began, result.status, f' ({result.error})' if result.error else '',
                                                      f' · {result.detail}' if result.detail else '')
                log_delivery(payload, result)
            except Exception:
                logging.getLogger(__name__).warning('n8n 백그라운드 전송 실패: event=%s', payload.get('event'), exc_info=True)

        task = asyncio.create_task(deliver())
        self._chains[key] = task
        self._pending.add(task)

        def finished(done):
            self._pending.discard(done)
            if self._chains.get(key) is done:
                del self._chains[key]
        task.add_done_callback(finished)

    async def flush(self, session_id: str | None = None) -> None:
        """대기 중인 전송이 끝나길 기다립니다(대화 종료 직전·서버 종료 시·테스트용)."""
        tasks = [self._chains[session_id]] if session_id in self._chains else ([] if session_id else list(self._pending))
        if tasks:
            await asyncio.wait(tasks)

    async def send_log(self, payload) -> WebhookDelivery:
        # 기록 서버의 장애로 대화를 중단하지 않으며 전송 결과도 호출자에게 반환합니다.
        if settings.n8n_webhook_url and settings.n8n_async:
            self.enqueue(payload)
            return WebhookDelivery(event=payload['event'],event_id=payload['event_id'],status='queued')
        if settings.n8n_webhook_url:
            began = time.monotonic()
            delivery = await self.n8n.send_event(payload)
            timing.record('n8n 호출', time.monotonic() - began, f"{payload.get('event')} {delivery.status}" + (f' · {delivery.detail}' if delivery.detail else ''))
        else:
            from app.integrations.n8n import DeliveryResult
            delivery = DeliveryResult('not_configured')
        log_delivery(payload,delivery)
        return WebhookDelivery(event=payload['event'],event_id=payload['event_id'],status=delivery.status,error=delivery.error)

    async def reply(self, conversation: Conversation, data: ChatRequest, progress=None) -> ChatResponse:
        """progress(event, payload): 스트리밍 응답용 async 콜백('status' 진행 문구, 'delta' 미리보기 문장)."""
        timings = timing.start(f'{conversation.employee_id} · "{data.message[:20]}{"…" if len(data.message) > 20 else ""}"')
        try:
            return await self._reply_timed(conversation, data, progress)
        finally:
            timings.log(TIMING_ORDER)

    async def _reply_timed(self, conversation: Conversation, data: ChatRequest, progress=None) -> ChatResponse:
        question_id = uuid4()
        question_at = datetime.now(timezone.utc)
        question_payload = self.event_payload(conversation,settings.n8n_event_question,
            message_id=str(question_id),question=data.message,asked_at=sheet_time(question_at),question_at=sheet_time(question_at),
            answer_at='',answer='',answer_status='PENDING',answer_source='',**HANDLER_BLANK)
        deliveries = [*conversation.webhook_events,await self.send_log(question_payload)]
        try:
            response = await self._reply(conversation,data,question_id,question_at,progress)
        except Exception:
            # 질문이 PENDING에 남지 않도록 생성 실패도 같은 message_id로 알립니다.
            await self.send_log(self.event_payload(conversation,settings.n8n_event_answer,
                message_id=str(question_id),question=data.message,answer='',answer_status='FAILED',answer_message_id='',processing_status='failed',category=None,tools_used=[],
                question_at=sheet_time(question_at),answer_at=sheet_time(),answer_source='',**HANDLER_BLANK,
                error_code='chat_processing_failed',answered_at=sheet_time()))
            raise
        answered_at = sheet_time()
        deliveries.append(await self.send_log(self.event_payload(conversation,settings.n8n_event_answer,
            message_id=str(question_id),answer_message_id=str(response.message_id),question=data.message,
            answer=strip_emphasis(response.answer),processing_status=response.status,
            **answer_sheet_fields(response,sheet_time(question_at),answered_at),
            category=response.tools_used[0] if response.tools_used else None,tools_used=response.tools_used,
            answered_at=answered_at)))
        response.webhook_events = deliveries
        return response

    async def _reply(self, conversation: Conversation, data: ChatRequest, question_id, question_at, progress=None) -> ChatResponse:
        async def say(event, payload):
            if progress is not None:
                await progress(event, payload)

        profile = await run_in_threadpool(self.users.get, conversation.employee_id)
        request = ToolInput(
            question=data.message, employee_id=conversation.employee_id,
            conversation_id=conversation.id,
            user_profile=profile,
        )
        history = await run_in_threadpool(
            self.repository.recent_messages, conversation.id, settings.history_message_limit,
        )
        marks = {'start': time.monotonic()}
        catalog = await self.tools.list_tools()
        # 도구 선택은 현재 질문만 보고 합니다. 이전 대화가 섞이면 새 주제도 직전 주제의 도구로 가기 쉽습니다.
        decision = await select_tools(request, data.tool_id, self.ollama, [], catalog)
        marks['routed'] = time.monotonic()
        if decision.tool_id == GENERAL_TOOL_ID:
            return await self._reply_general(conversation, data, question_id, question_at, request, history, profile,
                                             marks, data.tool_id is not None, progress)
        await say('status', '관련 규정을 검색하고 있습니다…')
        request.arguments = decision.arguments.model_dump()
        selected = [decision.tool_id]
        results = [await self.tools.execute(decision.tool_id, request)]
        marks['tools'] = time.monotonic()
        remote = results[0].data.pop('_timings', None) if isinstance(results[0].data, dict) else None
        for label, seconds in ((remote or {}).get('items') or {}).items():
            timing.record(label, seconds, ((remote or {}).get('notes') or {}).get(label, ''))
        await say('status', f'관련 문서 {len(results[0].sources)}개를 찾았습니다. 답변을 작성하고 있습니다…' if results[0].sources else '답변을 정리하고 있습니다…')
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
            async def preview(text):
                await say('delta', text)
            answer = await (self.ollama.generate_answer(context, on_preview=preview) if progress is not None
                            else self.ollama.generate_answer(context))
            answer = emphasize(answer)
            generated = bool(context.sources)  # 사원 조회 결과만 있으면 모델 호출 없이 사실을 정리합니다.
        else:
            import json
            excerpts = [f'[{index}] {source.document} p.{source.page or "?"}\n{source.text[:1200]}'
                        for index, source in enumerate(context.sources, 1)]
            answer = '검색/조회 결과 (답변 모델 미사용)\n\n' + '\n\n'.join(excerpts)
            if result.data:
                answer += '\n\n업무 조회/계산:\n' + json.dumps(result.data, ensure_ascii=False, indent=2)
        marks['answered'] = time.monotonic()
        if context.answer_coverage == 'unknown':
            context.answer_coverage = 'direct'
        needs_contact = context.answer_coverage in {'partial','missing'}
        if needs_contact:
            # 선택된 도구와 검색된 규정 문서명은 질문 표현이 겹칠 때 업무 주제를 정하는 보조 근거입니다.
            hints = ContactHints(tool_id=decision.tool_id,
                                 documents=tuple(dict.fromkeys(source.document for source in context.sources)))
            context.contact_escalation = await run_in_threadpool(
                self.contacts.recommend,data.message,conversation.employee_id,context.history,hints,
            )
        if context.answer_coverage == 'missing' and status == 'answered':
            status = 'needs_review'
        marks['contacts'] = time.monotonic()
        active = timing.current.get()
        if active is not None:
            active.add('도구 선택(툴콜링)', marks['routed']-marks['start'])
            retrieval = sum(active.items.get(name, 0) for name in ('임베딩', '벡터 검색', '표 복원'))
            active.add('도구 실행(그 외)', max(0.0, marks['tools']-marks['routed']-retrieval))
            active.add('답변 생성', marks['answered']-marks['tools'])
            active.add('담당자 조회', marks['contacts']-marks['answered'])
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
                Step(key="route", label="도구 선택", detail=names[0] + (' · 직접 지정' if data.tool_id else ' · Ollama 선택') + f" · {marks['routed']-marks['start']:.1f}초", status="done"),
                Step(key="tools", label="도구 실행", detail=f'{self.tools.transport} · ' + ('사원·부서 조회' if people_lookup else f'문서 근거 {len(context.sources)}개') + f" · {result.status} · {marks['tools']-marks['routed']:.1f}초", status="done"),
                Step(key="context", label="컨텍스트 구성", detail=f"사용자 정보 {'조회됨' if profile else '없음'} · 최근 메시지 {len(history)}개", status="done"),
                Step(key="generate", label="Ollama 답변 생성", detail=("Ollama 응답 완료" if generated else '조회 결과/추가 정보 안내') + f" · {marks['answered']-marks['tools']:.1f}초", status="done" if generated else "skipped"),
                *([Step(key='contacts',label='관련 담당자 조회',detail=f"업무 관련 문의 후보 {len(context.contact_escalation.contacts)}명 · {marks['contacts']-marks['answered']:.1f}초",
                        status='done' if context.contact_escalation.contacts else 'skipped')] if needs_contact else []),
                Step(key="return", label="답변 출력", detail=f"{self.repository.storage_name}에 질문·답변 저장 완료", status="done"),
            ],
        )

    async def _reply_general(self, conversation, data, question_id, question_at, request, history, profile,
                             marks, forced, progress=None) -> ChatResponse:
        """선택할 업무 도구가 없을 때: 문서 검색 없이 회사 챗봇으로서 일반 대화로 답합니다."""
        async def preview(text):
            if progress is not None:
                await progress('delta', text)
        if progress is not None:
            await progress('status', '답변을 작성하고 있습니다…')
        context = build_context(request, history, [])
        context.answer_coverage = 'direct'
        generated = False
        if settings.answer_provider == 'ollama':
            answer = await (self.ollama.generate_general(context, on_preview=preview) if progress is not None
                            else self.ollama.generate_general(context))
            generated = True
        else:
            answer = '업무 도구로 처리할 수 없는 일반 질문입니다. (답변 모델 미사용 모드)'
        marks['answered'] = time.monotonic()
        # 질문이 특정 업무 주제와 맞을 때만 담당자를 보여주고, 기본 창구는 붙이지 않습니다.
        context.contact_escalation = await run_in_threadpool(
            self.contacts.recommend, data.message, conversation.employee_id, context.history, None, False)
        marks['contacts'] = time.monotonic()
        active = timing.current.get()
        if active is not None:
            active.add('도구 선택(툴콜링)', marks['routed'] - marks['start'])
            active.add('답변 생성', marks['answered'] - marks['routed'])
            active.add('담당자 조회', marks['contacts'] - marks['answered'])
        assistant_id = uuid4()
        selected = [GENERAL_TOOL_ID]
        messages = [
            Message(id=question_id, role='user', content=data.message, created_at=question_at),
            Message(id=assistant_id, role='assistant', content=answer, created_at=datetime.now(timezone.utc),
                    sources=[], tools_used=selected, contact_escalation=context.contact_escalation),
        ]
        await run_in_threadpool(self.repository.append_turn, conversation.id, messages, context,
                                history[-1].id if history else None)
        contacts = context.contact_escalation.contacts
        return ChatResponse(
            conversation_id=conversation.id, message_id=assistant_id, answer=answer,
            sources=[], tools_used=selected, tool_results=[], context=context,
            mode=settings.mode, answer_provider=settings.answer_provider, status='answered',
            contact_escalation=context.contact_escalation,
            steps=[
                Step(key='receive', label='질문 접수', detail='FastAPI 요청 검증 완료', status='done'),
                Step(key='route', label='도구 선택', detail=f"{GENERAL_TOOL_NAME} · 맞는 업무 도구 없음"
                     + (' · 직접 지정' if forced else ' · Ollama 선택') + f" · {marks['routed']-marks['start']:.1f}초", status='done'),
                Step(key='context', label='컨텍스트 구성', detail=f"사용자 정보 {'조회됨' if profile else '없음'} · 최근 메시지 {len(history)}개 · 문서 검색 생략", status='done'),
                Step(key='generate', label='Ollama 답변 생성', detail=('일반 대화 답변' if generated else '모델 미사용') + f" · {marks['answered']-marks['routed']:.1f}초",
                     status='done' if generated else 'skipped'),
                *([Step(key='contacts', label='관련 담당자 조회', detail=f"업무 관련 문의 후보 {len(contacts)}명", status='done')] if contacts else []),
                Step(key='return', label='답변 출력', detail=f"{self.repository.storage_name}에 질문·답변 저장 완료", status='done'),
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
            "occurred_at": sheet_time(ended_at),
            "conversation_id": str(conversation.id), "employee_id": conversation.employee_id,
            "ended_at": sheet_time(ended_at), "rating": data.rating, "comment": data.comment,
            **satisfaction_fields(data.rating, data.comment),
            "started_at": sheet_time(conversation.created_at),
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
        await self.flush(str(conversation.id))  # 앞선 질문·답변 로그가 먼저 도착하도록 순서를 맞춥니다.
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
