"""Tool 공통 반환 형식, 입력 검사, 로그인 사원 문맥."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
import sqlite3
from typing import Any, Callable


class ToolError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def tool_result(function: Callable) -> Callable:
    """예상 가능한 오류를 Agent가 처리할 수 있는 dict로 반환합니다."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ToolError as exc:
            return {"status": "error", "error": {"code": exc.code, "message": str(exc)}}
        except sqlite3.Error:
            return {"status": "error", "error": {
                "code": "DATABASE_ERROR",
                "message": "SQLite 연결 및 sql_queries.json의 테이블·컬럼 매핑을 확인하세요.",
            }}
    return wrapped


def success(data: dict) -> dict:
    return {"status": "success", "data": data}


def text(value: Any, name: str, *, allow_empty: bool = False, maximum: int = 2000) -> str:
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value.strip()):
        raise ToolError("INVALID_INPUT", f"{name}은 길이 {maximum} 이내의 문자열이어야 합니다.")
    return value.strip()


def number(value: Any, name: str, *, minimum: str = "0") -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ToolError("INVALID_INPUT", f"{name}은 숫자여야 합니다.")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ToolError("INVALID_INPUT", f"{name}은 숫자여야 합니다.") from exc
    if not result.is_finite() or result < Decimal(minimum) or result > Decimal("1000000000000"):
        raise ToolError("INVALID_INPUT", f"{name}의 범위를 확인하세요.")
    return result


def integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ToolError("INVALID_INPUT", f"{name}은 {low}~{high} 사이의 정수여야 합니다.")
    return value


def iso_date(value: Any, name: str) -> date:
    if not isinstance(value, str):
        raise ToolError("INVALID_INPUT", f"{name}은 YYYY-MM-DD 형식이어야 합니다.")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ToolError("INVALID_INPUT", f"{name}은 YYYY-MM-DD 형식이어야 합니다.") from exc
    if result.isoformat() != value:
        raise ToolError("INVALID_INPUT", f"{name}은 YYYY-MM-DD 형식이어야 합니다.")
    return result


def today_korea() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


@dataclass(frozen=True)
class EmployeeContext:
    """서버에서 사원번호를 조회하여 생성합니다. LLM Tool 인자에는 포함하지 않습니다."""
    employee_id: str
    employee: dict
    repository: Any


def create_employee_context(employee_id: str, repository: Any) -> EmployeeContext:
    employee_id = text(employee_id, "사원번호", maximum=100)
    employee = repository.get_employee(employee_id)
    if employee is None:
        raise ToolError("EMPLOYEE_NOT_FOUND", "등록된 사원번호를 확인하세요.")
    if str(employee.get("employee_id")) != employee_id:
        raise ToolError("EMPLOYEE_MISMATCH", "DB 사원번호 매핑을 확인하세요.")
    return EmployeeContext(employee_id, employee, repository)
