"""python -m app.mcp.server: 기존 분야 도구를 stdio MCP 서버로 제공합니다."""

import logging
import sys
from typing import Annotated
from uuid import UUID

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from app import timing
from app.repositories.users import create_user_repository
from app.schemas import RequestModel, ToolArguments, ToolInput, ToolResult
from app.tools.base import Tool
from app.tools.registry import TOOLS


class MCPToolRequest(RequestModel):
    question: str = Field(min_length=1, max_length=4000)
    employee_id: str = Field(min_length=1, max_length=50)
    conversation_id: UUID
    arguments: ToolArguments = Field(default_factory=ToolArguments)


def create_server(tools: dict[str, Tool] | None = None, users=None) -> MCPServer:
    catalog = TOOLS if tools is None else tools
    users = create_user_repository('sqlite') if users is None else users
    server = MCPServer('ABC Electronics HR Tools', instructions=(
        '분야에 맞는 도구를 선택해 규정 근거와 업무 조회 결과를 받으세요. '
        '도구는 조회와 가정 계산만 수행하며 승인이나 인사 변경을 하지 않습니다.'
    ))

    def handler_for(tool: Tool):
        async def execute(request: Annotated[MCPToolRequest, Field(description='질문과 서버가 확인한 세션 식별값')]) -> ToolResult:
            # 프로필은 호출자가 만들어 넣지 않고 서버 저장소에서 다시 조회합니다.
            profile = await run_in_threadpool(users.get, request.employee_id)
            spans = timing.start('mcp')  # 검색 단계별 시간을 호출한 쪽(FastAPI)의 응답 시간 표에 넘깁니다
            result = await tool.execute(ToolInput(
                question=request.question, employee_id=request.employee_id,
                conversation_id=request.conversation_id, user_profile=profile,
                arguments=request.arguments.model_dump(),
            ))
            if spans.items:
                result.data['_timings'] = {'items': dict(spans.items), 'notes': dict(spans.notes)}
            return result
        return execute

    for tool in catalog.values():
        definition = tool.definition
        server.tool(
            name=definition.id, title=definition.name, description=definition.description,
            annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False,
                                        idempotent_hint=True, open_world_hint=False),
            meta={'definition': definition.model_dump(mode='json')},
        )(handler_for(tool))
    return server


def warm_up_search():
    """규정 검색은 이 프로세스에서 실행되므로, 임베딩 모델(bge-m3)과 Chroma를 시작 때 미리 올립니다.
    (첫 질문에서 모델을 읽느라 10초 넘게 걸리는 것을 막습니다. 실패해도 서버는 계속 동작합니다.)"""
    import time
    started = time.monotonic()
    try:
        from app.rag.embeddings import EmbeddingService
        from app.rag.vector_store import ChromaVectorStore
        EmbeddingService().embed_query('워밍업')
        ChromaVectorStore().fetch(['warm-up'])
        print(f'[mcp] 검색 워밍업 완료 ({time.monotonic() - started:.1f}초)', file=sys.stderr, flush=True)
    except Exception as exc:
        print(f'[mcp] 검색 워밍업 실패: {type(exc).__name__}', file=sys.stderr, flush=True)


def main():
    # stdout는 MCP JSON-RPC 전용입니다. 진단 로그는 stderr로 보냅니다.
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    from app.config import settings
    if settings.warm_up:
        import threading
        threading.Thread(target=warm_up_search, daemon=True).start()
    create_server().run(transport='stdio')


if __name__ == '__main__':
    main()
