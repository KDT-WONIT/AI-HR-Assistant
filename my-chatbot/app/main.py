import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router, service as chat_service
from app.config import settings
from app.errors import ConversationConflict, ModelUnavailable, StorageUnavailable, RagUnavailable, MCPUnavailable
from app.mcp.client import tool_gateway


logger = logging.getLogger('uvicorn.error')


def ollama_models() -> list[str]:
    if settings.answer_provider != 'ollama':
        return []
    return [model for model in dict.fromkeys([settings.ollama_model, settings.ollama_answer_model]) if model]


async def warm_up():
    """서버를 켤 때 임베딩 모델과 Ollama 모델을 미리 메모리에 올리고, 서버를 끌 때까지 유지합니다(keep_alive).
    실패해도 서비스에는 영향이 없습니다."""
    from starlette.concurrency import run_in_threadpool
    started = time.monotonic()
    if chat_service.tools.transport != 'mcp_stdio':  # MCP 모드에서는 검색이 별도 프로세스에서 돌며 그쪽에서 미리 올립니다
        try:
            from app.rag.embeddings import EmbeddingService
            await run_in_threadpool(EmbeddingService().embed_query, '워밍업')
            logger.info('워밍업: 임베딩 모델 준비 (%.1f초)', time.monotonic() - started)
        except Exception as exc:
            logger.warning('워밍업: 임베딩 모델을 미리 올리지 못했습니다: %s', exc)
    import httpx
    base = settings.ollama_base_url.rstrip('/')
    async with httpx.AsyncClient(timeout=settings.ollama_timeout, trust_env=False) as client:
        for model in ollama_models():
            began = time.monotonic()
            try:
                # 프롬프트 없이 호출하면 모델만 올립니다. 실제 호출과 같은 num_ctx여야 첫 질문 때 다시 로딩되지 않습니다.
                response = await client.post(f'{base}/api/generate', json={
                    'model': model, 'keep_alive': settings.keep_alive_value(), 'options': {'num_ctx': settings.ollama_num_ctx}})
                response.raise_for_status()
                logger.info('워밍업: Ollama 모델 %s 준비 (%.1f초)', model, time.monotonic() - began)
            except Exception as exc:
                logger.warning('워밍업: Ollama 모델 %s를 올리지 못했습니다(실행 여부·모델 설치 확인): %s', model, type(exc).__name__)
        try:  # 모델이 모두 동시에 올라와 있는지 확인합니다. 올리고 내리기를 반복하면 질문마다 3~12초 로딩이 붙습니다.
            running = (await client.get(f'{base}/api/ps')).json().get('models', [])
            loaded = {item.get('name') or item.get('model'): item for item in running}
            for name, item in loaded.items():
                size, vram = item.get('size') or 0, item.get('size_vram') or 0
                gpu = f'GPU {vram / size:.0%}' if size else 'GPU ?'
                logger.info('워밍업: 메모리 상주 %s · %.1fGB · %s', name, size / 1e9, gpu)
            missing = [model for model in ollama_models() if model not in loaded and f'{model}:latest' not in loaded]
            if missing:
                logger.warning(
                    '워밍업: 함께 올라오지 못한 모델이 있습니다: %s (현재 상주: %s). 원인은 둘 중 하나입니다. '
                    '(1) Ollama 서버의 OLLAMA_MAX_LOADED_MODELS가 1 → 환경 변수를 2 이상으로 설정하고 Ollama를 재시작하세요. '
                    '(2) VRAM 부족 → 질문 분류와 답변에 같은 모델을 쓰도록 OLLAMA_MODEL과 OLLAMA_ANSWER_MODEL을 맞추세요.',
                    ', '.join(missing), ', '.join(loaded) or '없음')
            else:
                logger.info('워밍업 완료: 모델 %d개 동시 상주', len(loaded))
        except Exception:
            pass


async def unload_models():
    """서버를 끌 때 Ollama 모델을 메모리에서 내립니다(keep_alive 0)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            for model in ollama_models():
                await client.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json={'model': model, 'keep_alive': 0})
        logger.info('Ollama 모델을 메모리에서 내렸습니다.')
    except Exception:
        logger.warning('종료 시 Ollama 모델을 내리지 못했습니다(Ollama가 설정된 시간 뒤 자동으로 내립니다).')


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    async with tool_gateway.connect():
        if settings.warm_up:
            task = asyncio.create_task(warm_up())  # 서버 시작은 막지 않고 백그라운드에서 진행합니다.
        try:
            yield
        finally:
            if task is not None and not task.done():
                task.cancel()
            if settings.warm_up and settings.ollama_unload_on_exit:
                await unload_models()
            try:  # 서버를 끄기 전에 아직 못 보낸 로그를 마저 보냅니다.
                await asyncio.wait_for(chat_service.flush(), timeout=settings.n8n_timeout + 5)
                await chat_service.n8n.aclose()
            except Exception:
                logger.warning('종료 전 n8n 전송을 모두 마치지 못했습니다.')

app = FastAPI(
    title="ABC Electronics AI HR Assistant",
    version="0.1.0",
    description="SQLite 직원·대화 기록, MCP 도구 서버·클라이언트, ChromaDB 검색과 Ollama 답변.",
    lifespan=lifespan,
)
app.include_router(router, prefix="/api")
app.mount("/static", StaticFiles(directory=settings.frontend_dir), name="static")


async def storage_error(request, error):
    return JSONResponse(status_code=503, content={"detail": str(error)})


async def conflict_error(request, error):
    return JSONResponse(status_code=409, content={"detail": str(error), "code": "conversation_conflict"})


async def model_error(request, error):
    # 화면에는 안내 문구만 보이므로, 실제 원인(Ollama 연결·타임아웃 등)은 서버 로그에 남깁니다.
    cause = error.__cause__
    logger.warning('모델 오류(502): %s | 원인: %s: %s', error, type(cause).__name__ if cause else '-', cause or '-')
    return JSONResponse(status_code=502, content={"detail": str(error)})


app.add_exception_handler(StorageUnavailable, storage_error)
app.add_exception_handler(RagUnavailable, storage_error)
app.add_exception_handler(ConversationConflict, conflict_error)
app.add_exception_handler(ModelUnavailable, model_error)
app.add_exception_handler(MCPUnavailable, storage_error)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(settings.frontend_dir / "index.html")
