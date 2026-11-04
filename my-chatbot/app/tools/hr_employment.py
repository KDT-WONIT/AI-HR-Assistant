"""인사 및 고용관리: 채용, 인사이동, 승진, 평가, 상벌, 퇴직, 직무."""

from app.schemas import ToolDefinition, ToolInput, ToolResult
from app.config import settings
from app.tools.base import Tool
from app.tools.execution import execute_domain

SOURCE_PATTERNS = ["인사규정","5직급","계약직","별정직","인사평가","상벌","퇴직","직무관리","임원추천","일용근로","프로젝트 계약근로","해외근무"]


async def execute(request: ToolInput) -> ToolResult:
    return await execute_domain("hr_employment", SOURCE_PATTERNS, request)


tool = Tool(
    definition=ToolDefinition(
        id="hr_employment", name="인사 및 고용관리",
        description="채용, 인사이동, 승진, 평가, 상벌, 퇴직, 직무. 사번·이름으로 사원 정보, 소속, 업무 역할, 이메일·내선·연락처 조회",
        data_path=str(settings.chroma_dir),
        source_patterns=SOURCE_PATTERNS,
    ),
    execute=execute,
)

