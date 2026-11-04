import asyncio
import unittest
import sys
from dataclasses import replace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from mcp import Client

from app.agent.service import ChatService
from app.errors import MCPUnavailable
from app.mcp.client import MCPToolGateway
from app.mcp.server import create_server
from app.repositories.memory import MemoryConversationRepository
from app.schemas import ChatRequest, Source, ToolDefinition, ToolInput, ToolResult, ToolDecision, UserProfile
from app.tools.base import Tool
from app.tools.registry import TOOLS


class WindowsMCPLoopTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Windows reload 호환 검사')
    def test_selector_loop_uses_a_stdio_worker_and_shuts_it_down(self):
        async def check():
            gateway = MCPToolGateway()
            async with gateway.connect():
                self.assertIsNot(gateway.loop,asyncio.get_running_loop())
                self.assertEqual({tool.id for tool in await gateway.list_tools()},set(TOOLS))
            self.assertFalse(gateway.ready)
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(check())


class MCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.profile = UserProfile(employee_id='EMP-A', name='테스트 직원', department='개발팀')
        self.users = Mock()
        self.users.get.return_value = self.profile
        self.request = ToolInput(question='규정?', employee_id='EMP-A', conversation_id=uuid4())

    def make_tool(self, name='custom_tool'):
        execute = AsyncMock(return_value=ToolResult(tool_id=name,status='ok',message='조회됨',sources=[
            Source(document='fixture.pdf',page=4,text='확인된 규정 근거'),
        ]))
        return Tool(ToolDefinition(id=name,name='가상 업무 분야',description='분야별 규정 검색',data_path=''),execute)

    async def test_stdio_server_exposes_the_current_catalog(self):
        gateway = MCPToolGateway()
        async with gateway.connect():
            self.assertEqual({tool.id for tool in await gateway.list_tools()},set(TOOLS))
            self.assertTrue(gateway.ready)
        self.assertFalse(gateway.ready)

    async def test_dynamic_catalog_and_structured_call_reloads_profile(self):
        tools = {f'custom_{index}':self.make_tool(f'custom_{index}') for index in range(12)}
        gateway = MCPToolGateway()
        async with gateway.connect(create_server(tools,self.users)):
            self.assertEqual(len(await gateway.list_tools()),12)
            result = await gateway.execute('custom_11',self.request)
        self.assertEqual(result.sources[0].page,4)
        forwarded = tools['custom_11'].execute.await_args.args[0]
        self.assertEqual(forwarded.user_profile,self.profile)
        self.assertEqual(forwarded.employee_id,'EMP-A')

    async def test_invalid_arguments_and_profile_spoof_are_rejected(self):
        tool = self.make_tool()
        async with Client(create_server({'custom_tool':tool},self.users)) as client:
            for fields in ({'arguments':{'requested_days':-1}}, {'user_profile':{'name':'가짜'}}, {'question':' '}):
                payload = self.request.model_dump(mode='json',exclude={'user_profile'}) | fields
                result = await client.call_tool('custom_tool',{'request':payload})
                self.assertTrue(result.is_error)
            self.assertTrue((await client.call_tool('missing',{})).is_error)
        tool.execute.assert_not_awaited()

    async def test_mcp_failure_does_not_save_half_a_turn(self):
        tool = self.make_tool()
        tool.execute.side_effect = RuntimeError('test failure')
        repository = MemoryConversationRepository()
        conversation = repository.create('EMP-A')
        gateway = MCPToolGateway()
        service = ChatService(repository,self.users,tools=gateway)
        service.ollama.choose_tools = AsyncMock(return_value=ToolDecision(tool_id='custom_tool'))
        async with gateway.connect(create_server({'custom_tool':tool},self.users)):
            with self.assertRaises(MCPUnavailable):
                await service.reply(conversation,ChatRequest(message='규정?',employee_id='EMP-A'))
        self.assertEqual(repository.get(conversation.id).messages,[])

    async def test_chat_uses_mcp_discovery_and_result_in_model_context(self):
        tool = self.make_tool()
        repository = MemoryConversationRepository()
        conversation = repository.create('EMP-A')
        gateway = MCPToolGateway()
        service = ChatService(repository,self.users,tools=gateway)
        service.ollama.choose_tools = AsyncMock(return_value=ToolDecision(tool_id='custom_tool'))
        service.ollama.generate_answer = AsyncMock(return_value='근거 기반 테스트 답변')
        async with gateway.connect(create_server({'custom_tool':tool},self.users)):
            answer = await service.reply(conversation,ChatRequest(message='규정?',employee_id='EMP-A'))
        self.assertEqual(service.ollama.choose_tools.await_args.args[1][0].id,'custom_tool')
        context = service.ollama.generate_answer.await_args.args[0]
        self.assertEqual(context.sources[0].text,'확인된 규정 근거')
        self.assertEqual(answer.answer,'근거 기반 테스트 답변')
        self.assertIn('mcp_stdio',answer.steps[2].detail)
        self.assertEqual(len(repository.get(conversation.id).messages),2)

    async def test_disconnected_gateway_fails_explicitly(self):
        with self.assertRaises(MCPUnavailable):
            await MCPToolGateway().execute('custom_tool',self.request)

    async def test_slow_mcp_tool_times_out_without_direct_execution_fallback(self):
        from app.config import settings
        tool = self.make_tool()
        async def slow(request):
            await asyncio.sleep(0.2)
            return ToolResult(tool_id='custom_tool',status='ok',message='늦은 응답')
        tool.execute.side_effect = slow
        gateway = MCPToolGateway()
        async with gateway.connect(create_server({'custom_tool':tool},self.users)):
            with patch('app.mcp.client.settings',replace(settings,mcp_timeout=0.02)):
                with self.assertRaises(MCPUnavailable):
                    await gateway.execute('custom_tool',self.request)
        self.assertEqual(tool.execute.await_count,1)
