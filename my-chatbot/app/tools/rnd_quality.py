"""연구개발 및 품질: R&D, 지식재산권, 품질경영."""

from app.schemas import ToolDefinition, ToolInput, ToolResult
from app.config import settings
from app.tools.base import Tool
from app.tools.execution import execute_domain

SOURCE_PATTERNS = ["연구개발","지식재산","품질경영"]


async def execute(request: ToolInput) -> ToolResult:
    return await execute_domain("rnd_quality", SOURCE_PATTERNS, request)


tool = Tool(
    definition=ToolDefinition(
        id="rnd_quality", name="연구개발 및 품질",
        description="R&D, 지식재산권, 품질경영",
        data_path=str(settings.chroma_dir),
        source_patterns=SOURCE_PATTERNS,
    ),
    execute=execute,
)

