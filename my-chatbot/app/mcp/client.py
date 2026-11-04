"""FastAPI 수명 동안 stdio MCP 자식 프로세스와 연결을 재사용합니다."""

import os
import asyncio
import sys
import threading
from concurrent.futures import Future
from contextlib import asynccontextmanager
from typing import Protocol

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from app.config import PROJECT_ROOT, settings
from app.errors import MCPUnavailable
from app.schemas import ToolDefinition, ToolInput, ToolResult


class ToolGateway(Protocol):
    transport: str
    ready: bool

    async def list_tools(self) -> list[ToolDefinition]: ...
    async def execute(self, tool_id: str, request: ToolInput) -> ToolResult: ...


class MCPToolGateway:
    transport = 'mcp_stdio'

    def __init__(self):
        self.client: Client | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    @property
    def ready(self) -> bool:
        return self.client is not None

    @asynccontextmanager
    async def connect(self, server=None):
        """server 인자는 프로토콜 통합 테스트의 메모리 연결용입니다."""
        if self.client is not None:
            raise RuntimeError('MCP 연결이 이미 열려 있습니다.')
        if server is None and sys.platform == 'win32' and isinstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop):
            # Uvicorn reload는 Selector를 사용해야 소켓 재시작이 가능합니다.
            # stdio는 별도 스레드의 Proactor에서 유지하고 RPC를 그 루프로 전달합니다.
            ready = Future()
            stopped = Future()
            def worker():
                async def run():
                    stop = asyncio.Event()
                    try:
                        async with self._connect():
                            ready.set_result((asyncio.get_running_loop(), stop))
                            await stop.wait()
                    except BaseException as exc:
                        if not ready.done():
                            ready.set_exception(exc)
                        raise
                try:
                    with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
                        runner.run(run())
                except BaseException as exc:
                    stopped.set_exception(exc)
                else:
                    stopped.set_result(None)
            thread = threading.Thread(target=worker, name='mcp-stdio-loop', daemon=True)
            thread.start()
            try:
                owner_loop, stop = await asyncio.wrap_future(ready)
                try:
                    yield self
                finally:
                    owner_loop.call_soon_threadsafe(stop.set)
                    await asyncio.wrap_future(stopped)
            finally:
                await asyncio.to_thread(thread.join, 5)
            return
        async with self._connect(server):
            yield self

    @asynccontextmanager
    async def _connect(self, server=None):
        if server is None:
            server = StdioServerParameters(
                command=sys.executable, args=['-m', 'app.mcp.server'], cwd=str(PROJECT_ROOT),
                env={**os.environ, 'PYTHONIOENCODING':'utf-8', 'PYTHONUNBUFFERED':'1'},
            )
        async with Client(server, read_timeout_seconds=settings.mcp_timeout) as client:
            self.client = client
            self.loop = asyncio.get_running_loop()
            try:
                await self.list_tools()  # 준비 단계에서 목록/스키마를 확인합니다.
                yield self
            finally:
                self.client = None
                self.loop = None

    async def _on_owner_loop(self, operation):
        if self.loop is not None and self.loop is not asyncio.get_running_loop():
            future = asyncio.run_coroutine_threadsafe(operation(), self.loop)
            return await asyncio.wrap_future(future)
        return await operation()

    def require_client(self) -> Client:
        if self.client is None:
            raise MCPUnavailable('MCP 도구 서버가 연결되지 않았습니다. 앱을 다시 시작해주세요.')
        return self.client

    async def list_tools(self) -> list[ToolDefinition]:
        return await self._on_owner_loop(self._list_tools)

    async def _list_tools(self) -> list[ToolDefinition]:
        client = self.require_client()
        try:
            tools = []
            cursor = None
            while True:
                page = await client.list_tools(cursor=cursor)
                for item in page.tools:
                    definition = ToolDefinition.model_validate((item.meta or {}).get('definition') or {
                        'id':item.name, 'name':item.title or item.name,
                        'description':item.description or '', 'data_path':'',
                    })
                    if definition.id != item.name:
                        raise ValueError('MCP 도구 ID 불일치')
                    tools.append(definition)
                cursor = page.next_cursor
                if cursor is None:
                    break
            if not tools or len({item.id for item in tools}) != len(tools):
                raise ValueError('MCP 도구 목록이 비었거나 중복되었습니다.')
            return tools
        except Exception as exc:
            raise MCPUnavailable('MCP 도구 목록을 가져오지 못했습니다. 서버 연결을 확인해주세요.') from exc

    async def execute(self, tool_id: str, request: ToolInput) -> ToolResult:
        return await self._on_owner_loop(lambda: self._execute(tool_id, request))

    async def _execute(self, tool_id: str, request: ToolInput) -> ToolResult:
        client = self.require_client()
        try:
            response = await client.call_tool(tool_id, {'request':request.model_dump(
                mode='json', exclude={'user_profile'},
            )}, read_timeout_seconds=settings.mcp_timeout)
            if response.is_error:
                raise ValueError('MCP tools/call 오류')
            result = ToolResult.model_validate(response.structured_content)
            if result.tool_id != tool_id or result.status in {'error', 'not_implemented'}:
                raise ValueError('MCP 도구 결과 불일치 또는 실행 오류')
            return result
        except Exception as exc:
            raise MCPUnavailable('MCP 도구 실행에 실패했습니다. DB·검색 모델·서버 로그를 확인해주세요.') from exc


class LocalToolGateway:
    """기존 단위 테스트용 어댑터. 실제 채팅 기본 경로는 MCP입니다."""
    transport = 'local_test'
    ready = True

    async def list_tools(self) -> list[ToolDefinition]:
        from app.tools.registry import TOOLS
        return [tool.definition for tool in TOOLS.values()]

    async def execute(self, tool_id: str, request: ToolInput) -> ToolResult:
        from app.tools.registry import TOOLS
        return await TOOLS[tool_id].execute(request)


tool_gateway = MCPToolGateway()
