"""로그인 사원을 고정하여 다섯 Tool을 등록하고 JSON 호출을 실행합니다."""
from __future__ import annotations

from copy import deepcopy
from functools import partial

from .common import ToolError, create_employee_context, tool_result
from .database import SqliteRepository
from . import rag_search_tool, leave_status_tool, contact_lookup_tool, travel_expense_tool, inquiry_history_tool


class EmployeeTools:
    def __init__(self, employee_id: str, repository: SqliteRepository | None = None,
                 rag: rag_search_tool.RegulationSearch | None = None):
        self.context = create_employee_context(employee_id, repository if repository is not None else SqliteRepository())
        self.rag = rag if rag is not None else rag_search_tool.RegulationSearch()
        modules = [rag_search_tool, leave_status_tool, contact_lookup_tool, travel_expense_tool, inquiry_history_tool]
        self.definitions = [deepcopy(module.TOOL_DEFINITION) for module in modules]
        self.functions = {"search_regulations": self.rag.search_regulations}
        for function in [leave_status_tool.get_leave_status, contact_lookup_tool.get_responsible_contact,
                         travel_expense_tool.calculate_travel_expense, inquiry_history_tool.search_inquiry_history]:
            self.functions[function.__name__] = partial(function, context=self.context)

    @tool_result
    def execute_tool(self, selection: dict) -> dict:
        try:
            from jsonschema import Draft202012Validator
        except ImportError as exc:
            raise ToolError("DEPENDENCY_MISSING", "jsonschema 패키지를 설치하세요.") from exc
        if not isinstance(selection, dict) or set(selection) != {"tool_name", "arguments"}:
            raise ToolError("INVALID_SELECTION", "tool_name과 arguments만 포함한 객체가 필요합니다.")
        name, arguments = selection["tool_name"], selection["arguments"]
        if not isinstance(name, str) or name not in self.functions:
            raise ToolError("UNKNOWN_TOOL", "등록되지 않은 Tool입니다.")
        if not isinstance(arguments, dict):
            raise ToolError("INVALID_ARGUMENTS", "arguments는 JSON 객체여야 합니다.")
        definition = next(item["function"] for item in self.definitions if item["function"]["name"] == name)
        errors = list(Draft202012Validator(definition["parameters"]).iter_errors(arguments))
        if errors:
            raise ToolError("INVALID_ARGUMENTS", errors[0].message)
        try:
            return self.functions[name](**arguments)
        except Exception as exc:
            raise ToolError("TOOL_EXECUTION_ERROR", "Tool 내부 실행에 실패했습니다. 서버에서 DB·모델 설정을 확인하세요.") from exc
