from app.schemas import AnswerContext, Message, ToolInput, ToolResult
from app.config import settings


def build_context(request: ToolInput, history: list[Message], results: list[ToolResult]) -> AnswerContext:
    return AnswerContext(
        question=request.question,
        employee_id=request.employee_id,
        user_profile=request.user_profile,
        user_profile_status="found" if request.user_profile is not None else "not_found",
        history=[{"role": item.role, "content": item.content} for item in history[-settings.history_message_limit:]],
        tool_results=results,
        sources=[source for result in results for source in result.sources],
    )
