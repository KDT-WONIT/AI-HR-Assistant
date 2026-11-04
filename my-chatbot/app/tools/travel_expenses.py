"""출장 및 여비: 국내외 출장, 여비, 전근여비."""

from app.schemas import ToolDefinition, ToolInput, ToolResult
from app.config import settings
from app.tools.base import Tool
from app.tools.execution import execute_domain

SOURCE_PATTERNS = ["여비규정"]


async def execute(request: ToolInput) -> ToolResult:
    return await execute_domain("travel_expenses", SOURCE_PATTERNS, request)


tool = Tool(
    definition=ToolDefinition(
        id="travel_expenses", name="출장 및 여비",
        description="국내외 출장 규정 검색, 현재 사원 직급에 따른 일반 출장 예상 여비 계산. trip에 실제 일정·거리·비용을 입력. 전근여비는 규정 검색",
        data_path=str(settings.chroma_dir),
        source_patterns=SOURCE_PATTERNS,
    ),
    execute=execute,
)

