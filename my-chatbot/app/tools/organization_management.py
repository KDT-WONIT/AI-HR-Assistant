"""조직 및 경영관리: 직제, 직무권한, 사규, 기록물, 이사회."""

from app.schemas import ToolDefinition, ToolInput, ToolResult
from app.config import settings
from app.tools.base import Tool
from app.tools.execution import execute_domain

SOURCE_PATTERNS = ["정관","직제","직무권한","사규관리","기록물","문서관리","ESG","이사회","임시조직","상임임원 복무"]


async def execute(request: ToolInput) -> ToolResult:
    return await execute_domain("organization_management", SOURCE_PATTERNS, request)


tool = Tool(
    definition=ToolDefinition(
        id="organization_management", name="조직 및 경영관리",
        description="직제, 직무권한, 사규, 기록물, 이사회. 부서 목록·부서별 인원·부서 위치·대표 내선과 소속 직원 조회. 본인의 이전 문의·질문·대화 이력 검색",
        data_path=str(settings.chroma_dir),
        source_patterns=SOURCE_PATTERNS,
    ),
    execute=execute,
)

