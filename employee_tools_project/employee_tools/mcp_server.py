"""한 로그인 사원에 고정된 stdio MCP 서버. 사원번호는 접속 값으로 전달합니다."""
from __future__ import annotations

import argparse

from .common import ToolError
from .tool_registry import EmployeeTools


def create_server(employee_tools: EmployeeTools):
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("employee-regulation-tools")

    @mcp.tool()
    def search_regulations(query: str, top_k: int = 5, source: str | None = None,
                           max_distance: float | None = None) -> dict:
        """규정과 원문 PDF 페이지를 검색합니다. 근거가 부족하면 담당자를 조회하세요."""
        return employee_tools.execute_tool({"tool_name": "search_regulations", "arguments": {
            "query": query, "top_k": top_k, "source": source, "max_distance": max_distance}})

    @mcp.tool()
    def get_leave_status(leave_type: str = "annual", as_of: str | None = None, planned_days: float = 0) -> dict:
        """접속 사원의 휴가 사용·예약·잔여량과 사용 계획 후 잔여량을 계산합니다."""
        return employee_tools.execute_tool({"tool_name": "get_leave_status", "arguments": {
            "leave_type": leave_type, "as_of": as_of, "planned_days": planned_days}})

    @mcp.tool()
    def get_responsible_contact(topic: str, limit: int = 3) -> dict:
        """답변할 수 없는 주제의 담당자 연락처를 담당자 DB에서 제공합니다."""
        return employee_tools.execute_tool({"tool_name": "get_responsible_contact", "arguments": {"topic": topic, "limit": limit}})

    @mcp.tool()
    def calculate_travel_expense(trip: dict) -> dict:
        """접속 사원의 직급으로 국내·국외 일반 출장 예상액을 계산합니다.

        필수: trip_type(domestic/overseas), start_date, end_date, destination_city.
        국내: distance_km(전체거리), same_city, 숙박시 domestic_region_type.
        국외: destination_country, lodging_nights, meal_days.
        선택: transport_cost_krw, lodging_cost_per_night(국내KRW/국외USD),
        transport_mode, lodging_provided, lodging_extra_approved, toll_cost_krw,
        exchange_rate_krw_per_usd, approval_date, exchange_rate_date,
        exchange_rate_basis(hana_cash_buy_opening), special_conditions.
        숙박 지역: special_city/metropolitan_city/special_autonomous/other.
        미정 금액은 partial, 특별 조건은 needs_review로 반환합니다.
        """
        return employee_tools.execute_tool({"tool_name": "calculate_travel_expense", "arguments": {"trip": trip}})

    @mcp.tool()
    def search_inquiry_history(query: str = "", limit: int = 10) -> dict:
        """접속 사원 본인의 문의 이력을 검색합니다. 빈 검색어는 최근 이력입니다."""
        return employee_tools.execute_tool({"tool_name": "search_inquiry_history", "arguments": {"query": query, "limit": limit}})

    return mcp


def main():
    parser = argparse.ArgumentParser(description="사원 규정 안내 MCP 서버")
    parser.add_argument("--employee-id", required=True, help="서버에서 확인한 접속 사원번호")
    args = parser.parse_args()
    try:
        server = create_server(EmployeeTools(args.employee_id))
    except (ToolError, ImportError) as exc:
        raise SystemExit(str(exc)) from exc
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
