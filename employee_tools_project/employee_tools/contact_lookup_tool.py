"""Tool 3: 답변할 수 없는 주제에 대해 등록된 담당자 정보를 제공합니다."""
from __future__ import annotations

import json
import re

from .common import EmployeeContext, ToolError, integer, success, text, tool_result


@tool_result
def get_responsible_contact(topic: str, limit: int = 3, *, context: EmployeeContext) -> dict:
    """규정의 결재자 이름을 추측하지 않고 담당자 DB의 활성 정보를 검색합니다."""
    topic = text(topic, "topic", maximum=500)
    limit = integer(limit, "limit", 1, 10)
    tokens = set(re.findall(r"[가-힣A-Za-z0-9]+", topic.casefold()))
    matched, general = [], []
    for row in context.repository.get_contacts():
        if not {"name", "department", "topic", "keywords_json", "phone", "email"}.issubset(row):
            raise ToolError("DB_MAPPING_ERROR", "담당자 정보의 필수 컬럼 매핑을 확인하세요.")
        try:
            keywords = json.loads(row["keywords_json"] or "[]")
        except (TypeError, ValueError) as exc:
            raise ToolError("CONTACT_DATA_ERROR", "keywords_json은 문자열 목록 JSON이어야 합니다.") from exc
        if not isinstance(keywords, list) or any(not isinstance(word, str) for word in keywords):
            raise ToolError("CONTACT_DATA_ERROR", "담당자 키워드는 문자열 목록이어야 합니다.")
        labels = [str(row["topic"]), *keywords]
        labels = [label.strip().casefold() for label in labels if label.strip()]
        score = sum(3 if label == topic.casefold() else 1 for label in labels
                    if label in topic.casefold() or any(token in label for token in tokens))
        if not row.get("phone") and not row.get("email"):
            continue
        item = {key: row.get(key) for key in ("contact_id", "name", "department", "topic", "phone", "email")}
        if row["topic"] == "general":
            general.append(item)
        elif score:
            # 동일 주제 후보 안에서만 소속 부서 담당자를 우선합니다.
            priority = score + (1 if row["department"] == context.employee.get("department") else 0)
            matched.append((priority, item))
    matched.sort(key=lambda pair: pair[0], reverse=True)
    contacts = [item for _, item in matched[:limit]] if matched else general[:limit]
    if not contacts:
        return {"status": "not_found", "message": "등록된 담당자 정보를 찾지 못했습니다. 담당자 DB 등록이 필요합니다.",
                "topic": topic, "contacts": []}
    return success({"topic": topic, "match_type": "topic" if matched else "registered_general_contact",
                    "contacts": contacts, "basis": "담당자 DB에 등록된 활성 정보"})


TOOL_DEFINITION = {
    "type": "function", "function": {
        "name": "get_responsible_contact", "description": "규정 근거 부족·예외 판단 등 답변 불가 주제의 등록 담당자와 연락처를 제공합니다.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "minLength": 1, "description": "답변 불가한 주제. 예: 연차 이월, 국외 출장 여비"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        }, "required": ["topic"], "additionalProperties": False},
    },
}
