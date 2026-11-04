"""Tool 2: 로그인 사원의 휴가 사용·예약·잔여 일수를 계산합니다."""
from __future__ import annotations

from decimal import Decimal

from .common import EmployeeContext, ToolError, iso_date, number, success, text, today_korea, tool_result


@tool_result
def get_leave_status(leave_type: str = "annual", as_of: str | None = None,
                     planned_days: float = 0, *, context: EmployeeContext) -> dict:
    """DB의 부여·이월·소멸 및 승인된 차감 내역을 기준으로 계산합니다.

    as_of는 한국 날짜, planned_days는 아직 등록하지 않은 사용 계획입니다.
    입사기념일 등 실제 계산기간은 DB에서 읽으며 1월~12월로 가정하지 않습니다.
    """
    leave_type = text(leave_type, "leave_type", maximum=100)
    기준일 = iso_date(as_of, "as_of") if as_of is not None else today_korea()
    planned = number(planned_days, "planned_days")
    balance = context.repository.get_leave_balance(context.employee_id, leave_type, 기준일.isoformat())
    if balance is None:
        return {"status": "not_found", "message": "해당 기준일의 휴가 부여정보가 없습니다."}
    required = {"period_start", "period_end", "granted_days", "carried_days", "adjustment_days", "expired_days"}
    if not required.issubset(balance):
        raise ToolError("DB_MAPPING_ERROR", "휴가 부여정보의 필수 컬럼 매핑을 확인하세요.")
    start = iso_date(balance["period_start"], "period_start")
    end = iso_date(balance["period_end"], "period_end")
    if not start <= 기준일 <= end:
        raise ToolError("INVALID_LEAVE_PERIOD", "휴가 부여기간과 기준일이 일치하지 않습니다.")
    granted = number(balance["granted_days"], "granted_days")
    carried = number(balance["carried_days"], "carried_days")
    adjustment = number(balance["adjustment_days"], "adjustment_days", minimum="-1000000")
    expired = number(balance["expired_days"], "expired_days")
    entitlement = granted + carried + adjustment - expired
    if entitlement < 0:
        raise ToolError("INVALID_BALANCE", "부여·조정·소멸 일수의 합계가 음수입니다.")
    used = scheduled = pending = Decimal("0")
    details = []
    for row in context.repository.get_leave_usage(context.employee_id, leave_type, start.isoformat(), end.isoformat()):
        if not {"used_on", "days", "status", "leave_type"}.issubset(row) or row["leave_type"] != leave_type:
            raise ToolError("DB_MAPPING_ERROR", "휴가 사용내역의 컬럼 및 휴가 종류 매핑을 확인하세요.")
        used_on = iso_date(row["used_on"], "used_on")
        days = number(row["days"], "휴가 차감일수")
        if not start <= used_on <= end:
            raise ToolError("INVALID_USAGE_PERIOD", "계산기간 밖의 휴가 내역이 반환되었습니다.")
        status = row["status"]
        if status == "approved":
            if used_on <= 기준일:
                used += days
            else:
                scheduled += days
        elif status == "pending":
            pending += days
        elif status not in {"cancelled", "rejected"}:
            raise ToolError("UNKNOWN_LEAVE_STATUS", "휴가 상태를 approved/pending/cancelled/rejected로 매핑하세요.")
        details.append({"usage_id": row.get("usage_id"), "date": used_on.isoformat(),
                        "days": float(days), "status": status})
    remaining = entitlement - used - scheduled
    return success({
        "employee_id": context.employee_id, "leave_type": leave_type, "as_of": 기준일.isoformat(),
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "granted_days": float(granted), "carried_days": float(carried),
        "adjustment_days": float(adjustment), "expired_days": float(expired),
        "entitlement_days": float(entitlement), "used_days": float(used),
        "scheduled_days": float(scheduled), "pending_days": float(pending),
        "unused_days": float(entitlement - used), "remaining_days": float(remaining),
        "planned_days": float(planned), "remaining_after_plan": float(remaining - planned),
        "plan_fits_balance": planned <= remaining, "balance_is_negative": remaining < 0,
        "usage": details,
        "basis": "승인된 미래 휴가는 예약분으로 차감합니다. 대기·취소·반려는 잔여량에서 제외합니다. 사용 계획은 DB에 저장하지 않습니다.",
    })


TOOL_DEFINITION = {
    "type": "function", "function": {
        "name": "get_leave_status", "description": "접속한 사원의 휴가 부여·사용·예약·잔여량과 사용 계획 후 잔여량을 조회합니다.",
        "parameters": {"type": "object", "properties": {
            "leave_type": {"type": "string", "description": "DB의 휴가 종류 코드. 기본 annual"},
            "as_of": {"type": ["string", "null"], "description": "기준일 YYYY-MM-DD. 생략하면 한국의 오늘"},
            "planned_days": {"type": "number", "minimum": 0, "description": "추가 사용 계획 일수. 예: 반일 0.5"},
        }, "additionalProperties": False},
    },
}
