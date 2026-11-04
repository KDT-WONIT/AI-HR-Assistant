"""보안 및 안전관리: 보안, 산업안전, 사고대응, 보상, 비상근무."""

from app.schemas import ToolDefinition, ToolInput, ToolResult
from app.config import settings
from app.tools.base import Tool
from app.tools.execution import execute_domain

SOURCE_PATTERNS = ["보상 및 배상","보안규정","비상근무","안전보건","안전사고"]


async def execute(request: ToolInput) -> ToolResult:
    return await execute_domain("security_safety", SOURCE_PATTERNS, request)


tool = Tool(
    definition=ToolDefinition(
        id="security_safety", name="보안 및 안전관리",
        description="보안, 산업안전, 사고대응, 보상, 비상근무",
        data_path=str(settings.chroma_dir),
        source_patterns=SOURCE_PATTERNS,
    ),
    execute=execute,
)

