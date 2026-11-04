"""감사 및 윤리준법: 감사, 법무, 이해충돌, 인권, 내부통제."""

from app.schemas import ToolDefinition, ToolInput, ToolResult
from app.config import settings
from app.tools.base import Tool
from app.tools.execution import execute_domain

SOURCE_PATTERNS = ["감사규정","법무","내부통제","이해충돌","인권경영","행동강령","청렴계약","적극행정"]


async def execute(request: ToolInput) -> ToolResult:
    return await execute_domain("audit_ethics", SOURCE_PATTERNS, request)


tool = Tool(
    definition=ToolDefinition(
        id="audit_ethics", name="감사 및 윤리준법",
        description="감사, 법무, 이해충돌, 인권, 내부통제",
        data_path=str(settings.chroma_dir),
        source_patterns=SOURCE_PATTERNS,
    ),
    execute=execute,
)

