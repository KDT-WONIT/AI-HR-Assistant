"""팀원의 SQLite DB를 읽는 어댑터. 실제 테이블명은 SQL 설정에서 매핑합니다."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .common import ToolError
from .paths import employee_db_path, sql_queries_path


class SqliteRepository:
    def __init__(self, db_path: str | Path | None = None, queries_path: str | Path | None = None):
        self.db_path = employee_db_path(db_path)
        if not self.db_path.is_file():
            raise ToolError("DB_NOT_FOUND", "팀원의 SQLite DB를 프로젝트의 data/employee/employee.sqlite3에 넣으세요.")
        query_file = sql_queries_path(queries_path)
        try:
            self.queries = json.loads(query_file.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ToolError("SQL_CONFIG_ERROR", "SQL 조회문 설정 파일을 확인하세요.") from exc
        required = {"employee", "leave_balance", "leave_usage", "contacts", "inquiries"}
        if not isinstance(self.queries, dict) or not required.issubset(self.queries):
            raise ToolError("SQL_CONFIG_ERROR", "SQL 설정에 employee/leave_balance/leave_usage/contacts/inquiries가 필요합니다.")
        if any(not isinstance(self.queries[key], str) for key in required):
            raise ToolError("SQL_CONFIG_ERROR", "SQL 설정값은 문자열이어야 합니다.")

    def _read(self, name: str, parameters: dict) -> list[dict]:
        # mode=ro는 잘못된 경로의 새 DB 생성과 쓰기를 막습니다.
        uri = self.db_path.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            rows = connection.execute(self.queries[name], parameters).fetchall()
        return [dict(row) for row in rows]

    def _owned(self, rows: list[dict], employee_id: str) -> list[dict]:
        # 잘못 수정한 SQL이 다른 사원의 행을 반환해도 노출하지 않습니다.
        if any(str(row.get("employee_id")) != employee_id for row in rows):
            raise ToolError("EMPLOYEE_SCOPE_ERROR", "조회문에 로그인 사원번호 조건이 필요합니다.")
        return rows

    def get_employee(self, employee_id: str) -> dict | None:
        rows = self._owned(self._read("employee", {"employee_id": employee_id}), employee_id)
        if len(rows) > 1:
            raise ToolError("DUPLICATE_EMPLOYEE", "사원번호가 중복되어 있습니다.")
        return rows[0] if rows else None

    def get_leave_balance(self, employee_id: str, leave_type: str, as_of: str) -> dict | None:
        params = {"employee_id": employee_id, "leave_type": leave_type, "as_of": as_of}
        rows = self._owned(self._read("leave_balance", params), employee_id)
        if len(rows) > 1:
            raise ToolError("DUPLICATE_BALANCE", "동일 기준일에 휴가 부여기간이 중복됩니다.")
        return rows[0] if rows else None

    def get_leave_usage(self, employee_id: str, leave_type: str, start: str, end: str) -> list[dict]:
        rows = self._read("leave_usage", {"employee_id": employee_id, "leave_type": leave_type,
                                         "period_start": start, "period_end": end})
        return self._owned(rows, employee_id)

    def get_contacts(self) -> list[dict]:
        return self._read("contacts", {})

    def search_inquiries(self, employee_id: str, keyword: str, limit: int) -> list[dict]:
        rows = self._read("inquiries", {"employee_id": employee_id, "keyword": keyword, "limit": limit})
        return self._owned(rows, employee_id)
