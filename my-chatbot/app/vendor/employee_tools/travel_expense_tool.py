"""Tool 4: 제공된 여비규정에 따른 국내·국외 일반 출장 예상액 계산.

정액·숙박 한도는 여비규정 개정번호 38에서 옮겼습니다.
실비 항목은 예상 지출액 또는 한도 예산으로 표시하며 지급 확정액이 아닙니다.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .common import EmployeeContext, ToolError, integer, iso_date, number, success, text, tool_result

SOURCE = "여비규정(2025년도 07월 개정).pdf"
DOCUMENT_ID = "a4a354aa1bc367fb47a51e53"
EFFECTIVE_FROM = "2025-08-04"
GRADES = {"executive", "grade_1", "grade_2", "grade_3", "grade_4_plus"}
OVERSEAS_RATES = {
    "executive": {"daily": 60, "A": (389, 160), "B": (289, 138)},
    "grade_1": {"daily": 40, "A": (176, 108), "B": (137, 92)},
    "grade_2": {"daily": 40, "A": (176, 108), "B": (137, 92)},
    "grade_3": {"daily": 35, "A": (140, 96), "B": (120, 83)},
    "grade_4_plus": {"daily": 30, "A": (140, 96), "B": (120, 83)},
}
A_CITIES = {"도쿄", "tokyo", "오사카", "osaka", "베이징", "beijing", "홍콩", "hongkong",
            "싱가포르", "singapore", "뉴욕", "newyork", "시카고", "chicago", "런던", "london",
            "파리", "paris", "오슬로", "oslo"}
REGION_CAPS = {"special_city": 100000, "metropolitan_city": 90000,
               "special_autonomous": 80000, "other": 70000}


def _money(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _citations(*numbers: int) -> list[dict]:
    pages = {18: 5, 21: 5, 26: 6, 34: 7, 36: 7, 40: 8, 49: 9, 53: 10,
             91: 15, 92: 15, 93: 15, 94: 15, 95: 15, 98: 16, 99: 16, 100: 16, 102: 16, 103: 16}
    return [{"source": SOURCE, "chunk_id": f"{DOCUMENT_ID}:{n:06d}", "pdf_pages": [pages[n]]}
            for n in dict.fromkeys(numbers)]


def _review(reason: str, *citations: int) -> dict:
    return {"status": "needs_review", "message": reason, "estimated_total_krw": None,
            "next_tool": "get_responsible_contact", "topic": "출장 여비",
            "sources": _citations(*citations)}


def _boolean(trip: dict, key: str, default: bool = False) -> bool:
    value = trip.get(key, default)
    if type(value) is not bool:
        raise ToolError("INVALID_INPUT", f"{key}은 true/false여야 합니다.")
    return value


def _amount(trip: dict, key: str) -> Decimal | None:
    return None if trip.get(key) is None else number(trip[key], key)


@tool_result
def calculate_travel_expense(trip: dict, *, context: EmployeeContext) -> dict:
    """직급은 로그인 사원 DB에서 읽습니다. 날짜는 출발·복귀일을 포함합니다.

    trip의 선택 항목은 TOOL_DEFINITION과 README를 참고하세요.
    미입력 교통비·환율 등을 0으로 간주하지 않고 partial로 반환합니다.
    """
    if not isinstance(trip, dict):
        raise ToolError("INVALID_INPUT", "trip은 JSON 객체여야 합니다.")
    allowed = set(TRIP_PROPERTIES)
    if set(trip) - allowed:
        raise ToolError("INVALID_INPUT", f"허용되지 않은 출장 항목: {sorted(set(trip) - allowed)}")
    required = {"trip_type", "start_date", "end_date", "destination_city"}
    if not required.issubset(trip):
        raise ToolError("MISSING_INPUT", f"필수 출장 항목: {sorted(required - set(trip))}")
    kind = trip["trip_type"]
    if kind not in {"domestic", "overseas"}:
        raise ToolError("INVALID_INPUT", "trip_type은 domestic 또는 overseas입니다.")
    start, end = iso_date(trip["start_date"], "start_date"), iso_date(trip["end_date"], "end_date")
    days = (end - start).days + 1
    if not 1 <= days <= 366:
        raise ToolError("INVALID_INPUT", "출장기간은 1~366일 범위여야 합니다.")
    if False and start.isoformat() < EFFECTIVE_FROM:
        return _review("해당 출장일에 적용되는 과거 규정 확인이 필요합니다.", 98)
    grade = context.employee.get("travel_grade")
    if grade not in GRADES:
        raise ToolError("TRAVEL_GRADE_NOT_MAPPED", "DB 직급을 executive/grade_1/grade_2/grade_3/grade_4_plus로 매핑하세요.")
    city = text(trip["destination_city"], "destination_city", maximum=100)
    special = trip.get("special_conditions", [])
    if not isinstance(special, list) or any(not isinstance(item, str) for item in special):
        raise ToolError("INVALID_INPUT", "special_conditions는 문자열 목록이어야 합니다.")
    if special:
        return _review("동행·파견·분할 출장·기관 부담·부분 식사 제공 등 특별 조건은 담당자 확인이 필요합니다: " + ", ".join(special), 18, 21, 26, 40, 95)
    mode = trip.get("transport_mode", "public_transport")
    if mode not in {"public_transport", "private_car", "company_car", "rental_car"}:
        raise ToolError("INVALID_INPUT", "transport_mode 값을 확인하세요.")
    lodging_provided = _boolean(trip, "lodging_provided")
    extra_approved = _boolean(trip, "lodging_extra_approved")
    missing, notes = [], []
    transport = _amount(trip, "transport_cost_krw")
    toll = _amount(trip, "toll_cost_krw") or Decimal("0")
    if kind == "overseas" and ("lodging_nights" not in trip or "meal_days" not in trip):
        raise ToolError("MISSING_INPUT", "국외 출장은 기내 체류를 제외한 lodging_nights와 meal_days를 명시하세요.")
    nights = integer(trip.get("lodging_nights", days - 1), "lodging_nights", 0, days - 1)
    meal_days = integer(trip.get("meal_days", days), "meal_days", 0, days)
    if kind == "domestic":
        if "distance_km" not in trip or "same_city" not in trip:
            raise ToolError("MISSING_INPUT", "국내 출장은 전체 출장거리 distance_km와 동일 시·군 여부 same_city가 필요합니다.")
        distance = number(trip["distance_km"], "distance_km", minimum="0.001")
        same_city = _boolean(trip, "same_city")
        if distance < 50 or same_city:
            if mode == "company_car":
                return _review("회사차량 근거리여비는 제20조제5항의 통행료 등 실비 지급과 별표3의 18,000원 지급 주석 간 적용관계 확인이 필요합니다.", 40, 103)
            if days != 1 or nights or distance >= 50 or mode == "rental_car" or meal_days != days:
                return _review("숙박·복수일·동일 시군 50km 이상·렌터카·식사 제공 근거리 출장은 지급 방식 확인이 필요합니다.", 40, 102)
            allowance = Decimal(20000 if distance < 10 else 30000 if distance < 25 else 40000)
            return success({"employee_id": context.employee_id, "trip_type": kind, "travel_grade": grade,
                            "destination_city": city, "days": days, "currency": "KRW",
                            "estimate_type": "near_distance_flat_allowance",
                            "estimated_total_krw": _money(allowance),
                            "notes": ["별표3 정액은 교통비·일비·식비를 포함하므로 별도 중복 가산하지 않습니다."],
                            "sources": _citations(40, 102)})
        if mode == "private_car":
            return _review("장거리 자가차량은 연료비와 철도·버스운임 한도 및 예외 승인 확인이 필요합니다.", 36)
        if mode == "company_car":
            return _review("회사 제공 차량에 대한 일비 제외 범위는 담당자 확인이 필요합니다. 교통비와 통행료의 기준은 제17조제5항을 따릅니다.", 18, 36)
        daily_rate = Decimal(30000 if grade == "executive" else 25000)
        meal_rate = Decimal(60000 if grade == "executive" else 30000)
        # 도착일은 기본 일비, 도착 다음 날부터 30일/다음 30일/초과분을 적용합니다.
        after_arrival = days - 1
        daily_units = (Decimal(1 + min(after_arrival, 30))
                       + Decimal(min(max(after_arrival - 30, 0), 30)) * Decimal("0.9")
                       + Decimal(max(after_arrival - 60, 0)) * Decimal("0.8"))
        if mode == "rental_car":
            daily_units *= Decimal("0.5")
        meals = meal_rate * meal_days
        if days == 1 and nights == 0:
            meals *= Decimal(2) / Decimal(3)
        lodging_rate = _amount(trip, "lodging_cost_per_night")
        cap = None
        if grade not in {"executive", "grade_1"}:
            region = trip.get("domestic_region_type")
            if nights and not lodging_provided and region not in REGION_CAPS:
                raise ToolError("MISSING_INPUT", "숙박 지역 구분 domestic_region_type이 필요합니다.")
            cap = Decimal(REGION_CAPS.get(region, 70000))
        currency = "KRW"
        citations = [18, 34, 36, 40, 98, 99, 100]
    else:
        if days > 28:
            return _review("국외 1개월 초과 체재의 일비 80% 적용기간은 담당자에게 확인해야 합니다. 이 계산기는 28일 이내 일반 출장에 적용합니다.", 95)
        if mode == "private_car":
            return _review("국외 자가차량 교통비는 별도 확인이 필요합니다.", 49)
        if mode == "company_car":
            return _review("국외 회사 제공 차량에 대한 일비 제외 범위는 담당자 확인이 필요합니다.", 18, 26)
        country = text(trip.get("destination_country"), "destination_country", maximum=100)
        compact_city = "".join(city.casefold().split())
        region = "A" if compact_city in A_CITIES or country.casefold() in {"스위스", "switzerland"} else "B"
        rates = OVERSEAS_RATES[grade]
        cap, meal_rate = (Decimal(value) for value in rates[region])
        daily_rate = Decimal(rates["daily"])
        daily_units = Decimal(days)
        if mode == "rental_car":
            daily_units *= Decimal("0.5")
        meals = meal_rate * meal_days
        lodging_rate = _amount(trip, "lodging_cost_per_night")
        currency = "USD"
        citations = [18, 49, 53, 91, 92, 93, 94, 95]
        notes.append("국외 숙박 예상 단가는 USD, 교통비·통행료 예상액은 KRW로 입력합니다.")
    if lodging_provided or nights == 0:
        lodging = Decimal("0")
        lodging_basis = "provided_or_no_overnight"
    else:
        if extra_approved:
            if cap is None:
                notes.append("실비 직급에는 정액 숙박 한도를 가산하지 않습니다.")
            else:
                cap *= Decimal("1.3" if kind == "domestic" else "1.5")
                notes.append("증빙과 소속부서장 승인을 받은 숙박비 초과 한도를 반영했습니다.")
        if lodging_rate is None:
            lodging = cap * nights if cap is not None else None
            lodging_basis = "ceiling_budget" if cap is not None else "missing_expected_cost"
            if cap is None:
                missing.append("lodging_cost_per_night")
            else:
                notes.append("숙박 예상 단가가 없어 한도액 전액을 예산으로 사용했습니다. 실제 지급액은 증빙 실비입니다.")
        else:
            lodging = min(lodging_rate, cap) * nights if cap is not None else lodging_rate * nights
            lodging_basis = "expected_cost_within_cap"
            if cap is not None and lodging_rate > cap:
                notes.append("입력한 숙박 단가 중 인정 한도를 넘는 금액은 제외했습니다.")
    daily = daily_rate * daily_units
    known_allowances = daily + meals + (lodging or Decimal("0"))
    if transport is None:
        missing.append("transport_cost_krw")
    if kind == "overseas":
        rate = _amount(trip, "exchange_rate_krw_per_usd")
        if rate is None:
            missing.append("exchange_rate_krw_per_usd")
            known_krw = None
        else:
            if rate <= 0:
                raise ToolError("INVALID_INPUT", "환율은 0보다 커야 합니다.")
            approval = iso_date(trip.get("approval_date"), "approval_date")
            rate_date = iso_date(trip.get("exchange_rate_date"), "exchange_rate_date")
            if approval != rate_date:
                raise ToolError("EXCHANGE_RATE_DATE_MISMATCH", "환율 기준일은 해외출장계획 품의일자와 같아야 합니다.")
            if approval > start:
                raise ToolError("INVALID_INPUT", "품의일자는 출장 시작일보다 늦을 수 없습니다.")
            if trip.get("exchange_rate_basis") != "hana_cash_buy_opening":
                raise ToolError("EXCHANGE_RATE_BASIS_REQUIRED", "하나은행 품의일 현찰 살 때 시초가를 확인하고 exchange_rate_basis를 hana_cash_buy_opening으로 지정하세요.")
            known_krw = known_allowances * rate + (transport or Decimal("0")) + toll
    else:
        known_krw = known_allowances + (transport or Decimal("0")) + toll
    total = known_krw if not missing else None
    result = {"employee_id": context.employee_id, "trip_type": kind, "travel_grade": grade,
              "destination_city": city, "start_date": start.isoformat(), "end_date": end.isoformat(),
              "days": days, "lodging_nights": nights, "meal_days": meal_days, "allowance_currency": currency,
              "daily_allowance": _money(daily), "meal_allowance": _money(meals),
              "lodging_budget": _money(lodging), "lodging_basis": lodging_basis,
              "lodging_cap_per_night": _money(cap), "transport_cost_krw": _money(transport),
              "toll_cost_krw": _money(toll), "known_allowances_subtotal": _money(known_allowances),
              "known_subtotal_krw": _money(known_krw), "estimated_total_krw": _money(total),
              "missing_inputs": missing, "estimate_type": "ordinary_business_trip_budget",
              "notes": notes + ["식사·숙소·차량 제공, 동행 등 추가 조건이 있으면 입력해야 합니다.",
                                "표시 금액은 소수 둘째 자리 반올림입니다. 실제 정산 시 절사·승인·증빙을 별도 확인해야 합니다."],
              "policy_effective_from": EFFECTIVE_FROM, "sources": _citations(*citations)}
    if kind == "overseas":
        result["overseas_region_grade"] = region
        result["exchange_rate_krw_per_usd"] = _money(rate)
    return {"status": "partial" if missing else "success", "data": result}


TRIP_PROPERTIES = {
    "trip_type": {"type": "string", "enum": ["domestic", "overseas"]},
    "start_date": {"type": "string", "description": "출발일 YYYY-MM-DD"},
    "end_date": {"type": "string", "description": "복귀일 YYYY-MM-DD"},
    "destination_city": {"type": "string", "minLength": 1},
    "destination_country": {"type": "string", "description": "국외 출장 국가. 스위스는 모든 도시 가등급"},
    "distance_km": {"type": "number", "exclusiveMinimum": 0, "description": "국내 전체 출장거리(왕복 포함)"},
    "same_city": {"type": "boolean", "description": "근무지와 동일 시·군인지"},
    "domestic_region_type": {"type": "string", "enum": list(REGION_CAPS),
                             "description": "특별시/광역시/특별자치시·도/기타"},
    "transport_mode": {"type": "string", "enum": ["public_transport", "private_car", "company_car", "rental_car"]},
    "transport_cost_krw": {"type": ["number", "null"], "minimum": 0, "description": "규정에 맞는 등급의 교통비 예상 총액(원). 미정이면 생략"},
    "toll_cost_krw": {"type": "number", "minimum": 0, "description": "교통비에 중복 포함하지 않은 별도 통행료"},
    "lodging_nights": {"type": "integer", "minimum": 0, "description": "유상 지상 숙박 밤 수. 국외는 필수"},
    "lodging_cost_per_night": {"type": ["number", "null"], "minimum": 0, "description": "예상 1박 단가. 국내 KRW/국외 USD"},
    "lodging_provided": {"type": "boolean"},
    "lodging_extra_approved": {"type": "boolean", "description": "증빙과 부서장 승인을 받은 숙박비 30%/50% 추가 한도"},
    "meal_days": {"type": "integer", "minimum": 0, "description": "식비 지급 대상 일수. 국외는 기내·무료 제공일을 제외하여 명시"},
    "exchange_rate_krw_per_usd": {"type": ["number", "null"], "exclusiveMinimum": 0},
    "approval_date": {"type": "string", "description": "국외출장계획 품의일 YYYY-MM-DD"},
    "exchange_rate_date": {"type": "string"},
    "exchange_rate_basis": {"type": "string", "enum": ["hana_cash_buy_opening"]},
    "special_conditions": {"type": "array", "items": {"type": "string"},
                           "description": "임원 동행, 여러 도시, 기관 비용 부담, 부분 식사 제공, 마일리지 가산, 분할 장기 출장 등. 있으면 담당자 확인으로 전환"},
}

TOOL_DEFINITION = {
    "type": "function", "function": {
        "name": "calculate_travel_expense", "description": "로그인 사원의 직급과 회사 여비규정으로 국내·국외 일반 출장 예상액을 계산합니다. 실제 정산 확정 기능이 아닙니다.",
        "parameters": {"type": "object", "properties": {"trip": {
            "type": "object", "properties": TRIP_PROPERTIES,
            "required": ["trip_type", "start_date", "end_date", "destination_city"],
            "additionalProperties": False,
        }}, "required": ["trip"], "additionalProperties": False},
    },
}
