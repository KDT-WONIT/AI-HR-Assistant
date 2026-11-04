import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import FileResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.agent.service import ChatService
from app.config import settings
from app.errors import StorageUnavailable
from app.repositories.factory import create_repository
from app.repositories.directory import EmployeeDirectoryRepository
from app.schemas import (
    ChatRequest, ChatResponse, Conversation, ConversationCreate,
    EndRequest, EndResponse, ToolDefinition, UserLookupResponse, EmployeePage, DepartmentProfile,
)
from app.tools.registry import TOOLS

router = APIRouter()
repository = create_repository()
service = ChatService(repository)
background: set = set()  # 스트리밍 처리 작업이 중간에 정리되지 않도록 참조를 유지합니다
directory = EmployeeDirectoryRepository()


def require_answer_provider():
    if settings.mode == "live" and settings.answer_provider != "ollama":
        raise HTTPException(501, "실제 답변은 ANSWER_PROVIDER=ollama와 모델 설정이 필요합니다.")


async def get_conversation(conversation_id: UUID, *, include_messages: bool = True) -> Conversation:
    conversation = await run_in_threadpool(repository.get, conversation_id, include_messages=include_messages)
    if conversation is None:
        raise HTTPException(404, "대화를 찾을 수 없습니다. 대화 ID와 저장소 설정을 확인해주세요.")
    return conversation


@router.get("/health", tags=["system"])
async def health():
    storage_status = "ready"
    try:
        await run_in_threadpool(repository.ping)
    except StorageUnavailable:
        storage_status = "unavailable"
    directory_status = 'not_selected'
    if settings.user_data_source == 'directory':
        try:
            await run_in_threadpool(directory.ping)
            directory_status = 'ready'
        except StorageUnavailable:
            directory_status = 'unavailable'
    ready = storage_status == 'ready' and directory_status != 'unavailable' and service.tools.ready
    return {
        "status": "ok" if ready else "degraded",
        "mode": settings.mode, "storage": repository.storage_name,
        "storage_status": storage_status, "answer_provider": settings.answer_provider,
        "history_message_limit": settings.history_message_limit,
        "chat_available": ready,
        "user_data_source": settings.user_data_source,
        "tool_router": settings.tool_router,
        "tool_count": len(TOOLS),
        "tool_transport": service.tools.transport,
        "integrations": {
            "ollama": "configured" if settings.answer_provider == "ollama" else "not_configured",
            "mysql": storage_status if repository.storage_name == "mysql" else "not_selected",
            "sqlite": storage_status if repository.storage_name == 'sqlite' else 'not_selected',
            "chroma": "configured", "n8n": "configured" if settings.n8n_webhook_url else "not_configured",
            "mcp": "ready" if service.tools.ready else "unavailable",
            "employee_directory": directory_status,
        },
    }


@router.get("/tools", response_model=list[ToolDefinition], tags=["tools"])
async def list_tools():
    return await service.tools.list_tools()


@router.get("/users/{employee_id}", response_model=UserLookupResponse, tags=["users"])
async def resolve_user(employee_id: str = Path(min_length=1, max_length=50)):
    profile = await run_in_threadpool(service.users.get, employee_id)
    return UserLookupResponse(
        employee_id=employee_id, status="found" if profile is not None else "not_found", profile=profile,
    )


@router.get('/users/{employee_id}/photo', tags=['users'])
async def employee_photo(employee_id: str = Path(min_length=1,max_length=50),
                         fallback: bool = Query(default=False,description='true이면 외부 사진 없이 로컬 파일만 반환')):
    photo = await run_in_threadpool(directory.photo,employee_id)
    # 내려받은 실제 사진(JPG 등)이 없으면 사원 DB의 사진 주소를 브라우저가 직접 불러오게 합니다.
    if (photo is None or photo.suffix.lower() == '.svg') and not fallback:
        remote = await run_in_threadpool(directory.remote_photo_url,employee_id)
        if remote:
            return RedirectResponse(remote,status_code=307,headers={'Cache-Control':'private, max-age=3600'})
    if photo is None:
        raise HTTPException(404,'등록된 로컬 프로필 이미지가 없습니다.')
    return FileResponse(photo,headers={'X-Content-Type-Options':'nosniff',
                                      'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; sandbox"})


@router.get('/employees',response_model=EmployeePage,tags=['directory'])
async def employees(query: str = Query(default='',max_length=100), department_id: str | None = Query(default=None,max_length=50),
                    limit: int = Query(default=20,ge=1,le=50),offset: int = Query(default=0,ge=0)):
    return await run_in_threadpool(directory.search,query.strip(),department_id,limit,offset)


@router.get('/departments',response_model=list[DepartmentProfile],tags=['directory'])
async def departments():
    return await run_in_threadpool(directory.departments)


@router.post("/conversations", response_model=Conversation, status_code=201, tags=["conversations"])
async def create_conversation(data: ConversationCreate):
    return await service.start_conversation(data.employee_id)


@router.get("/conversations/{conversation_id}", response_model=Conversation, tags=["conversations"])
async def read_conversation(conversation_id: UUID):
    return await get_conversation(conversation_id)


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(data: ChatRequest):
    require_answer_provider()
    if data.tool_id is not None and data.tool_id not in TOOLS:
        raise HTTPException(422, "등록되지 않은 도구입니다.")
    conversation = (
        await get_conversation(data.conversation_id, include_messages=False)
        if data.conversation_id else await service.start_conversation(data.employee_id)
    )
    if conversation.employee_id != data.employee_id:
        raise HTTPException(409, "대화에 설정된 사번과 요청 사번이 다릅니다.")
    if conversation.status == "closed":
        raise HTTPException(409, "종료된 대화입니다. 새 대화를 시작해주세요.")
    return await service.reply(conversation, data)


@router.post("/chat/stream", tags=["chat"])
async def chat_stream(data: ChatRequest):
    """답변을 만드는 동안 진행 상황과 미리보기 문장을 SSE로 보내고, 마지막에 검증된 최종 답변(final)을 보냅니다.
    이벤트: status(진행 문구) · delta(미리보기, 매번 전체 교체) · final(/chat과 같은 응답) · error."""
    import asyncio
    import json
    from fastapi.responses import StreamingResponse
    from app.errors import (ConversationConflict, MCPUnavailable, ModelUnavailable, RagUnavailable, StorageUnavailable)

    require_answer_provider()
    if data.tool_id is not None and data.tool_id not in TOOLS:
        raise HTTPException(422, "등록되지 않은 도구입니다.")
    conversation = (
        await get_conversation(data.conversation_id, include_messages=False)
        if data.conversation_id else await service.start_conversation(data.employee_id)
    )
    if conversation.employee_id != data.employee_id:
        raise HTTPException(409, "대화에 설정된 사번과 요청 사번이 다릅니다.")
    if conversation.status == "closed":
        raise HTTPException(409, "종료된 대화입니다. 새 대화를 시작해주세요.")

    queue: asyncio.Queue = asyncio.Queue()

    async def progress(event, payload):
        queue.put_nowait((event, payload))

    async def run():
        try:
            response = await service.reply(conversation, data, progress)
            queue.put_nowait(('final', response.model_dump(mode='json')))
        except (ModelUnavailable, RagUnavailable, StorageUnavailable, MCPUnavailable, ConversationConflict) as error:
            status = 409 if isinstance(error, ConversationConflict) else 502 if isinstance(error, ModelUnavailable) else 503
            queue.put_nowait(('error', {'detail': str(error), 'status': status}))
        except Exception:
            logging.getLogger('uvicorn.error').exception('스트리밍 응답 처리 중 오류')
            queue.put_nowait(('error', {'detail': '답변을 만드는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.', 'status': 500}))
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(run())  # 연결이 끊겨도 저장·로그 전송까지 끝까지 처리합니다.
    background.add(task)
    task.add_done_callback(background.discard)

    async def events():
        while (item := await queue.get()) is not None:
            event, payload = item
            yield f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/conversations/{conversation_id}/end", response_model=EndResponse, tags=["conversations"])
async def end_conversation(conversation_id: UUID, data: EndRequest):
    conversation = await get_conversation(conversation_id, include_messages=False)
    return await service.end(conversation, data)


@router.post('/conversations/{conversation_id}/webhook/retry', response_model=EndResponse, tags=['conversations'])
async def retry_webhook(conversation_id: UUID):
    await get_conversation(conversation_id, include_messages=False)
    return await service.deliver_end_event(conversation_id)
