from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RequestModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ConversationCreate(RequestModel):
    employee_id: str = Field(default="TEST-001", min_length=1, max_length=50)


class ChatRequest(ConversationCreate):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None
    tool_id: str | None = None


class EndRequest(RequestModel):
    rating: Literal["helpful", "neutral", "unhelpful"] | None = None
    comment: str = Field(default="", max_length=1000)


class Source(BaseModel):
    document: str
    page: int | None = None
    section: str | None = None
    text: str = ""
    chunk_id: str | None = None
    pages: list[int] = Field(default_factory=list)
    distance: float | None = None
    # 표 조각을 복원했을 때의 표 제목·단위와, 사용자 직급 등 관심어가 들어간 행(핵심 내용으로 출력)
    caption: str = ''
    highlights: list[str] = Field(default_factory=list)


class UserProfile(RequestModel):
    """사용자 DB에서 컨텍스트에 전달하는 기본 프로필 필드."""

    employee_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    job_title: str | None = Field(default=None, max_length=100)
    hired_at: date | None = None
    grade: str | None = None
    employment_type: str | None = None
    employment_status: str | None = None
    dept_id: str | None = None
    department_function: str | None = None
    department_location: str | None = None
    department_extension: str | None = None
    work_email: str | None = None
    extension_number: str | None = None
    work_location: str | None = None
    roles: list[str] = Field(default_factory=list)
    image_url: str | None = None
    photo_alt: str | None = None


class EmployeePage(BaseModel):
    items: list[UserProfile]
    total: int
    limit: int
    offset: int


class DepartmentProfile(BaseModel):
    dept_id: str
    dept_name: str
    parent_dept_id: str | None = None
    dept_function: str | None = None
    location: str | None = None
    main_extension: str | None = None
    employee_count: int = 0


class ContactRecommendation(BaseModel):
    employee: UserProfile
    reason: str
    matched_terms: list[str] = Field(default_factory=list)
    duty_description: str = ''
    match_type: Literal['related_duties'] = 'related_duties'


class ContactEscalation(BaseModel):
    status: Literal['not_needed','recommended','not_found','unavailable'] = 'not_needed'
    message: str = ''
    contacts: list[ContactRecommendation] = Field(default_factory=list)


class UserLookupResponse(BaseModel):
    employee_id: str
    status: Literal["found", "not_found"]
    profile: UserProfile | None = None


class ToolDefinition(BaseModel):
    id: str
    name: str
    description: str
    data_path: str
    status: Literal["ready", "not_implemented"] = "ready"
    source_patterns: list[str] = Field(default_factory=list)


class ToolInput(BaseModel):
    question: str
    employee_id: str
    conversation_id: UUID
    user_profile: UserProfile | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolArguments(RequestModel):
    year: int | None = Field(default=None, ge=1900, le=2200)
    requested_days: float | None = Field(default=None, gt=0, le=366, allow_inf_nan=False)
    department: str | None = Field(default=None, max_length=100)
    history_query: str | None = Field(default=None,max_length=500)
    history_limit: int = Field(default=5,ge=1,le=10)
    trip: dict[str,Any] | None = None


class ToolDecision(RequestModel):
    tool_id: str
    arguments: ToolArguments = Field(default_factory=ToolArguments)


class ToolResult(BaseModel):
    tool_id: str
    status: Literal["ok", "no_result", "needs_input", "not_implemented", "error"]
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[Source] = Field(default_factory=list)


class Step(BaseModel):
    key: str
    label: str
    detail: str
    status: Literal["done", "demo", "skipped"]


class AnswerContext(BaseModel):
    question: str
    employee_id: str
    user_profile: UserProfile | None = None
    user_profile_status: Literal["found", "not_found"] = "not_found"
    history: list[dict[str, str]] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    answer_coverage: Literal['unknown','direct','partial','missing'] = 'unknown'
    contact_escalation: ContactEscalation = Field(default_factory=ContactEscalation)


class WebhookDelivery(BaseModel):
    event: str
    event_id: UUID
    status: Literal['sent','failed','not_configured','queued']
    error: str | None = None


class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    status: Literal["needs_implementation", "answered", "no_result", "needs_input", "needs_review"] = "answered"
    sources: list[Source] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    context: AnswerContext
    steps: list[Step]
    mode: Literal["demo", "live"] = "demo"
    answer_provider: Literal["demo", "ollama"] = "demo"
    contact_escalation: ContactEscalation = Field(default_factory=ContactEscalation)
    webhook_events: list[WebhookDelivery] = Field(default_factory=list)


class Message(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    sources: list[Source] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    contact_escalation: ContactEscalation = Field(default_factory=ContactEscalation)


class EndResponse(BaseModel):
    conversation_id: UUID
    status: Literal["closed"] = "closed"
    ended_at: datetime
    rating: Literal["helpful", "neutral", "unhelpful"] | None
    comment: str
    event_id: UUID
    webhook_status: Literal["not_configured", "not_implemented", "pending", "sending", "sent", "failed"]
    message: str


class Conversation(BaseModel):
    id: UUID
    employee_id: str
    created_at: datetime
    status: Literal["open", "closed"] = "open"
    messages: list[Message] = Field(default_factory=list)
    end_result: EndResponse | None = None
    webhook_events: list[WebhookDelivery] = Field(default_factory=list)
