"""Tool 5: 접속 사원번호를 기준으로 본인의 문의 이력을 검색합니다."""
from __future__ import annotations

import re

from .common import EmployeeContext, ToolError, integer, success, text, tool_result


@tool_result
def search_inquiry_history(query: str = "", limit: int = 10, *, context: EmployeeContext) -> dict:
    """질문·답변·분류에서 키워드를 검색합니다. 빈 검색어는 최근 이력입니다."""
    query = text(query, "query", allow_empty=True, maximum=500)
    limit = integer(limit, "limit", 1, 50)
    tokens = list(dict.fromkeys(re.findall(r"[가-힣A-Za-z0-9]+", query.casefold())))[:8]
    terms = ([query] + tokens) if query else [""]
    candidates = {}
    for term in dict.fromkeys(terms):
        for row in context.repository.search_inquiries(context.employee_id, term, 100):
            if not {"inquiry_id", "question", "answer", "category", "created_at", "status"}.issubset(row):
                raise ToolError("DB_MAPPING_ERROR", "문의 이력 컬럼 매핑을 확인하세요.")
            candidates[row["inquiry_id"]] = row
    ranked = []
    for row in candidates.values():
        searchable = " ".join(str(row.get(key) or "") for key in ("question", "answer", "category")).casefold()
        score = sum(1 for token in tokens if token in searchable)
        if query and query.casefold() in searchable:
            score += 3
        item = {key: row.get(key) for key in ("inquiry_id", "question", "answer", "category", "created_at", "status")}
        item["match_score"] = score
        ranked.append(item)
    ranked.sort(key=lambda item: (item["match_score"], str(item["created_at"])), reverse=True)
    items = ranked[:limit]
    return success({"employee_id": context.employee_id,
                    "employee_department": context.employee.get("department"),
                    "query": query, "count": len(items), "results": items,
                    "scope": "current_employee_only", "search_method": "keyword",
                    "basis": "과거 답변은 현재 규정과 다시 대조해야 합니다."})


TOOL_DEFINITION = {
    "type": "function", "function": {
        "name": "search_inquiry_history", "description": "접속한 사원의 과거 문의·답변·처리 상태를 키워드로 검색합니다. 다른 사원의 이력은 조회하지 않습니다.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "검색어. 생략하면 최근 문의"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        }, "additionalProperties": False},
    },
}
