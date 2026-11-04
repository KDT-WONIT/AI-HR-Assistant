from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def compact_end_payload(payload: dict, messages: list[dict]) -> dict:
    """전체 RAG 컨텍스트 대신 최근 대화와 기본 업무 프로필만 보냅니다."""
    recent = messages[-settings.n8n_message_limit:]
    return {**payload, 'message_count':len(messages), 'turn_count':sum(m['role']=='user' for m in messages),
            'messages':[{'role':m['role'], 'content':m['content'][:settings.n8n_message_max_chars],
                         'created_at':m['created_at'], 'truncated':len(m['content']) > settings.n8n_message_max_chars}
                        for m in recent], 'history_truncated':len(recent) < len(messages)}


# 구글 시트(세션 시트 / 질문·답변 시트) 열 이름과 같은 필드명으로 보냅니다. 값이 없으면 빈 문자열입니다.
def sheet_time(value=None) -> str:
    """시트와 같은 시각 형식(UTC, 밀리초, Z)입니다. 예: 2026-11-04T01:59:17.993Z. 값이 없으면 현재 시각입니다."""
    moment = value or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


SATISFACTION_SCORES = {'helpful': 5, 'neutral': 3, 'unhelpful': 1}
HANDLER_BLANK = {'handler_id': '', 'handler_name': '', 'handler_department': '', 'handler_contact': ''}


def satisfaction_fields(rating, comment) -> dict:
    """만족도(helpful/neutral/unhelpful)를 시트의 satisfaction_score(1~5)·satisfaction_comment로 바꿉니다."""
    return {'satisfaction_score': SATISFACTION_SCORES.get(rating), 'satisfaction_comment': comment or ''}


def handler_fields(escalation) -> dict:
    """추천된 첫 번째 담당자를 시트의 handler_* 열로 바꿉니다. 없으면 모두 빈 값입니다."""
    contacts = getattr(escalation, 'contacts', None) or []
    if not contacts:
        return dict(HANDLER_BLANK)
    employee = contacts[0].employee
    return {'handler_id': employee.employee_id or '', 'handler_name': employee.name or '',
            'handler_department': employee.department or '',
            'handler_contact': employee.work_email or employee.extension_number or ''}


def answer_sheet_fields(response, question_at: str, answer_at: str) -> dict:
    """답변 이벤트의 시트 열. 담당자 안내로 넘어간 경우 ESCALATED / HR_ROUTING으로 기록합니다."""
    escalated = response.contact_escalation.status == 'recommended' and response.status in {'no_result', 'needs_review', 'needs_input'}
    if escalated:
        source = 'HR_ROUTING'
    elif response.sources:
        source = 'RAG'
    elif any(result.data for result in response.tool_results):
        source = 'TOOL'
    else:
        source = ''
    return {'question_at': question_at, 'answer_at': answer_at, 'answer_status': 'ESCALATED' if escalated else 'ANSWERED',
            'answer_source': source, **handler_fields(response.contact_escalation)}


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    error: str | None = None
    detail: str = ''  # 예: '연결 0.3초 · n8n 응답 대기 5.6초'


class N8nClient:
    def __init__(self):
        self._client = None
        self._loop = None

    def http(self):
        """연결을 재사용하는 클라이언트(호출마다 TLS 연결을 새로 맺는 시간을 없앱니다). 이벤트 루프가 바뀌면 새로 만듭니다."""
        loop = asyncio.get_running_loop()
        if self._client is None or self._loop is not loop or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=settings.n8n_timeout, trust_env=False, follow_redirects=False)
            self._loop = loop
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def send_conversation_ended(self, payload: dict) -> DeliveryResult:
        return await self.send_event(payload)

    async def send_event(self, payload: dict) -> DeliveryResult:
        if not settings.n8n_webhook_url:
            return DeliveryResult('not_configured')
        try:
            marks = {}

            async def trace(name, info):  # 연결 시간과 n8n 응답 대기 시간을 나눠 잽니다.
                marks[name] = time.monotonic()

            began = time.monotonic()
            response = await self.http().post(settings.n8n_webhook_url, json=payload,
                                              headers={'Idempotency-Key':payload['event_id'],
                                                       'Content-Type':'application/json; charset=utf-8'},
                                              extensions={'trace': trace})
            done = time.monotonic()
            sent = marks.get('http11.send_request_body.complete') or marks.get('http11.send_request_headers.complete')
            first_byte = marks.get('http11.receive_response_headers.complete')
            if sent and first_byte:
                detail = f'연결·전송 {sent - began:.1f}초 · n8n 응답 대기 {first_byte - sent:.1f}초 · 수신 {done - first_byte:.1f}초'
            else:
                detail = ''
            if not 200 <= response.status_code < 300:
                return DeliveryResult('failed', f'HTTP {response.status_code}', detail)
            # n8n이 HTTP 200으로 검증 실패를 응답하는 경우도 성공으로 숨기지 않습니다.
            try:
                body = response.json()
            except ValueError:
                body = None
            if isinstance(body,dict) and body.get('ok') is False:
                return DeliveryResult('failed','receiver_rejected', detail)
            return DeliveryResult('sent', None, detail)
        except httpx.TimeoutException:
            return DeliveryResult('failed', 'timeout')
        except (httpx.HTTPError, httpx.InvalidURL, ValueError):
            return DeliveryResult('failed', 'connection_error')


def log_delivery(payload: dict, result: DeliveryResult) -> None:
    if result.status == 'failed':
        # URL·연락처·질문 내용은 로그에 남기지 않습니다.
        logger.warning('n8n delivery failed: event=%s event_id=%s error=%s',
                       payload['event'],payload['event_id'],result.error)
