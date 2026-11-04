"""계약 및 재무회계: 계약, 공정거래, 회계, 내부회계, 출자회사."""

from app.schemas import ToolDefinition, ToolInput, ToolResult
from app.config import settings
from app.tools.base import Tool
from app.tools.execution import execute_domain

SOURCE_PATTERNS = ["계약규정","공정거래","회계","출자회사"]


async def execute(request: ToolInput) -> ToolResult:
    return await execute_domain("contracts_finance", SOURCE_PATTERNS, request)


tool = Tool(
    definition=ToolDefinition(
        id="contracts_finance", name="계약 및 재무회계",
        description="계약, 공정거래, 회계, 내부회계, 출자회사",
        data_path=str(settings.chroma_dir),
        source_patterns=SOURCE_PATTERNS,
    ),
    execute=execute,
)

