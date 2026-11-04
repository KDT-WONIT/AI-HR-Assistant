"""근무 및 노사관리: 근태, 연차, 휴직, 노사협의, 고충처리."""

from app.schemas import ToolDefinition, ToolInput, ToolResult
from app.config import settings
from app.tools.base import Tool
from app.tools.execution import execute_domain

SOURCE_PATTERNS = ["취업규칙","노사협의","고충처리"]


async def execute(request: ToolInput) -> ToolResult:
    return await execute_domain("work_labor", SOURCE_PATTERNS, request)


tool = Tool(
    definition=ToolDefinition(
        id="work_labor", name="근무 및 노사관리",
        description="근태, 연차, 휴직, 노사협의, 고충처리",
        data_path=str(settings.chroma_dir),
        source_patterns=SOURCE_PATTERNS,
    ),
    execute=execute,
)

