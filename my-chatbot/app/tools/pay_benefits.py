"""급여 및 복리후생: 연봉, 수당, 복지, 사택, 학자금, 주택융자."""

from app.schemas import ToolDefinition, ToolInput, ToolResult
from app.config import settings
from app.tools.base import Tool
from app.tools.execution import execute_domain

SOURCE_PATTERNS = ["연봉규정","복리후생","사택","학자금","주택융자","임금피크"]


async def execute(request: ToolInput) -> ToolResult:
    return await execute_domain("pay_benefits", SOURCE_PATTERNS, request)


tool = Tool(
    definition=ToolDefinition(
        id="pay_benefits", name="급여 및 복리후생",
        description="연봉, 수당, 복리후생, 복지, 사택, 학자금, 주택융자(주택 구입·임차를 위한 사내 대출·주택자금 대여), 임금피크",
        data_path=str(settings.chroma_dir),
        source_patterns=SOURCE_PATTERNS,
    ),
    execute=execute,
)

