from app.agent.general import GENERAL_TOOL_ID
from app.config import settings
from app.errors import ModelUnavailable
from app.schemas import ToolDecision, ToolDefinition, ToolInput


async def select_tools(request: ToolInput, forced_tool_id: str | None, client, history: list[dict],
                       tools: list[ToolDefinition]) -> ToolDecision:
    if forced_tool_id:
        if forced_tool_id not in {tool.id for tool in tools} | {GENERAL_TOOL_ID}:
            raise ModelUnavailable('MCP 서버에 등록되지 않은 도구입니다.')
        return ToolDecision(tool_id=forced_tool_id)
    if settings.tool_router == 'manual':
        raise ModelUnavailable('현재 수동 선택 모드입니다. 업무 분야를 직접 선택해주세요.')
    return await client.choose_tools(
        request.question, tools, history=history,
        profile=request.user_profile.model_dump(mode='json') if request.user_profile else None,
    )
