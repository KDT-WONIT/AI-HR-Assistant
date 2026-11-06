"""메인 화면 출장 여비 계산기(전체 입력 폼) 결과를 계산 과정·규정과 함께 보여줍니다.

금액은 계산 도구가 만든 값만 사용하며 모델이 만들지 않습니다.
규정 발췌는 계산에 인용된 규정 조각 원문을 그대로 보여줍니다."""
from decimal import Decimal

EXCERPT_LIMIT = 3
EXCERPT_CHARS = 160
TRIP_LABEL = {'domestic': '국내', 'overseas': '국외'}


FUEL_WON_PER_KM = 150   # 연비 약 11km/L, 휘발유 약 1,650원/L 가정
TOLL_WON_PER_KM = 50    # 고속도로 통행료 대략치
RENTAL_WON_PER_DAY = 60000  # 중형 렌터카 1일 대여료 대략치
PUBLIC_WON_PER_KM = 130     # 철도·버스 운임 대략치
OVERSEAS_FARE_WON = 800000  # 국외 왕복 항공 등 운임 가정
ASSUMED_USD_KRW = 1400      # 환율 가정


def estimate_vehicle(trip, assumptions):
    """국내 장거리 자가용·회사 제공 차량·대여 차량: 담당자 확인으로 멈추지 않고 교통비를 추정해 일반 계산으로 보냅니다.

    규정상 최종 지급액은 증빙으로 확정되므로, 계산기는 추정 교통비 + 일비·식비·숙박비 방식으로 계산하고
    추정한 가정은 모두 답변에 표시합니다. 근거리(50km 미만·동일 시·군) 정액 계산은 건드리지 않습니다.
    """
    mode = trip.get('transport_mode')
    if mode not in ('private_car', 'company_car', 'rental_car') or trip.get('trip_type') != 'domestic':
        return
    try:
        distance = float(trip.get('distance_km'))
    except (TypeError, ValueError):
        return
    if distance < 50 or trip.get('same_city'):
        return
    try:
        from datetime import date
        days = (date.fromisoformat(str(trip['end_date'])) - date.fromisoformat(str(trip['start_date']))).days + 1
    except (KeyError, ValueError):
        days = 1
    fuel = int(round(distance * FUEL_WON_PER_KM, -2))
    toll = int(round(distance * TOLL_WON_PER_KM, -2))
    if mode == 'private_car':
        trip['transport_mode'] = 'public_transport'  # 담당자 확인 분기를 피해 일반 계산으로
        if trip.get('transport_cost_krw') in (None, ''):
            trip['transport_cost_krw'] = fuel
            assumptions.append(f'교통비(추정): 자가용 연료비를 거리 {distance:g}km × km당 약 {FUEL_WON_PER_KM}원 = {fuel:,}원으로 추정했습니다.')
        if trip.get('toll_cost_krw') in (None, ''):
            trip['toll_cost_krw'] = toll
            assumptions.append(f'통행료(추정): 거리 {distance:g}km × km당 약 {TOLL_WON_PER_KM}원 = {toll:,}원으로 추정했습니다.')
        assumptions.append('자가용 교통비는 규정상 철도·버스운임 한도 안에서 인정되며 실제 지급액은 증빙으로 확정됩니다.')
    elif mode == 'company_car':
        trip['transport_mode'] = 'public_transport'
        if trip.get('transport_cost_krw') in (None, ''):
            trip['transport_cost_krw'] = 0
            assumptions.append('교통비(추정): 회사 제공 차량이라 개인 교통비는 0원으로 가정했습니다.')
        if trip.get('toll_cost_krw') in (None, ''):
            trip['toll_cost_krw'] = 0
            assumptions.append('통행료(추정): 회사 차량 통행료는 회사가 직접 부담하는 것으로 보고 0원으로 가정했습니다.')
        assumptions.append('회사 제공 차량의 일비 제외 범위는 확정되지 않아 일비를 정상 지급하는 것으로 가정했습니다. 담당자 확인이 필요할 수 있습니다.')
    else:  # rental_car: 일비 50% 감액은 계산기가 처리합니다.
        rental = RENTAL_WON_PER_DAY * days
        if trip.get('transport_cost_krw') in (None, ''):
            trip['transport_cost_krw'] = rental + fuel
            assumptions.append(f'교통비(추정): 렌터카 대여료 {RENTAL_WON_PER_DAY:,}원 × {days}일 + 연료비 {fuel:,}원 = {rental + fuel:,}원으로 추정했습니다.')
        if trip.get('toll_cost_krw') in (None, ''):
            trip['toll_cost_krw'] = toll
            assumptions.append(f'통행료(추정): 거리 {distance:g}km × km당 약 {TOLL_WON_PER_KM}원 = {toll:,}원으로 추정했습니다.')


estimate_private_car = estimate_vehicle  # 이전 이름 호환


def relax_for_estimate(trip, message=''):
    """담당자 확인(needs_review)으로 멈춘 조건을 계산 가능한 일반 출장 조건으로 완화합니다.
    반환: (완화된 입력, 설명 목록). 완화할 수 없으면 None."""
    trip = dict(trip)
    notes = []
    if trip.get('special_conditions'):
        notes.append('특별 조건(' + ', '.join(map(str, trip['special_conditions'])) + ')은 계산에 반영하지 못했습니다. 담당자 확인이 필요합니다.')
        trip['special_conditions'] = []
    if trip.get('trip_type', 'domestic') == 'domestic':
        try:
            distance = float(trip.get('distance_km'))
        except (TypeError, ValueError):
            distance = None
        if distance is not None and (distance < 50 or trip.get('same_city')):
            trip['distance_km'] = max(distance, 50)
            trip['same_city'] = False
            notes.append('근거리 정액 규정(당일·식사 미제공 등)에 맞지 않아 일반 출장(왕복 50km 이상, 다른 시·군) 기준으로 추정했습니다.')
            assumptions = []
            estimate_vehicle(trip, assumptions)
            notes.extend(assumptions)
        else:
            return None if not notes else (trip, notes)
        return trip, notes
    if trip.get('transport_mode') in ('private_car', 'company_car'):
        trip['transport_mode'] = 'public_transport'
        notes.append('국외 자가·회사 제공 차량 교통비는 확정할 수 없어 대중교통 기준으로 추정했습니다. 교통비는 별도로 입력해야 합니다.')
        return trip, notes
    return (trip, notes) if notes else None


def apply_defaults(trip):
    """필수 입력(출장지·기간·교통수단) 외 값이 비어 있어도 계산되도록 기본 가정을 채우고 가정 목록을 돌려줍니다."""
    from datetime import date
    trip = {k: v for k, v in trip.items() if v not in (None, '')}
    assumptions = []
    trip.setdefault('trip_type', 'domestic')
    try:
        days = (date.fromisoformat(str(trip['end_date'])) - date.fromisoformat(str(trip['start_date']))).days + 1
    except (KeyError, ValueError):
        return trip, assumptions
    if trip['trip_type'] == 'domestic':
        if 'distance_km' not in trip or 'same_city' not in trip:
            trip.setdefault('same_city', False)
            trip.setdefault('distance_km', 100)
            assumptions.append('거리·동일 시·군 여부가 없어 근무지와 다른 시·군의 원거리(50km 이상) 출장으로 계산했습니다.')
        if days > 1 and 'lodging_nights' not in trip:
            assumptions.append(f'숙박 밤 수가 없어 {days - 1}박으로 계산했습니다.')
        if days > 1 and trip.get('lodging_nights', days - 1) and 'domestic_region_type' not in trip:
            trip['domestic_region_type'] = 'other'
            assumptions.append('숙박 지역이 없어 "기타" 지역 기준(1박 상한 70,000원)으로 계산했습니다.')
        estimate_vehicle(trip, assumptions)
        if trip.get('transport_mode', 'public_transport') == 'public_transport' and trip.get('transport_cost_krw') in (None, ''):
            cost = int(round(float(trip['distance_km']) * PUBLIC_WON_PER_KM, -2))
            trip['transport_cost_krw'] = cost
            assumptions.append(f'교통비(추정): 대중교통 운임을 거리 {float(trip["distance_km"]):g}km × km당 약 {PUBLIC_WON_PER_KM}원 = {cost:,}원으로 추정했습니다.')
    else:
        if 'destination_country' not in trip:
            trip['destination_country'] = trip.get('destination_city', '')
            assumptions.append('국가가 없어 출장지를 기준으로 지역 등급을 판단했습니다.')
        if 'lodging_nights' not in trip:
            trip['lodging_nights'] = max(days - 1, 0)
            assumptions.append(f'숙박 밤 수가 없어 {max(days - 1, 0)}박으로 계산했습니다.')
        if 'meal_days' not in trip:
            trip['meal_days'] = days
            assumptions.append(f'식비 지급 일수가 없어 출장 {days}일 전체로 계산했습니다.')
        if trip.get('transport_mode') in ('private_car', 'company_car'):
            trip['transport_mode'] = 'public_transport'
            assumptions.append('국외 자가·회사 제공 차량 교통비는 확정할 수 없어 항공 등 대중교통 기준으로 추정했습니다.')
        if trip.get('transport_cost_krw') in (None, '') and trip.get('transport_mode', 'public_transport') in ('public_transport', 'rental_car'):
            trip['transport_cost_krw'] = OVERSEAS_FARE_WON
            assumptions.append(f'교통비(추정): 국외 왕복 항공 등 운임을 {OVERSEAS_FARE_WON:,}원으로 가정했습니다.')
        if 'exchange_rate_krw_per_usd' not in trip:
            from datetime import date as _date
            approval = min(_date.today(), _date.fromisoformat(str(trip['start_date'])))
            trip.setdefault('approval_date', approval.isoformat())
            trip.setdefault('exchange_rate_date', trip['approval_date'])
            trip.setdefault('exchange_rate_basis', 'hana_cash_buy_opening')
            trip['exchange_rate_krw_per_usd'] = ASSUMED_USD_KRW
            assumptions.append(f'환율이 없어 {ASSUMED_USD_KRW:,}원/USD로 가정했습니다. 실제는 품의일 하나은행 현찰 살 때 시초가를 적용합니다.')
    if 'meal_days' not in trip:
        assumptions.append(f'식비 지급 일수가 없어 출장 {days}일 전체로 계산했습니다.')
    return trip, assumptions


def _num(value):
    return None if value in (None, '') else Decimal(str(value))


def _fmt(value, currency):
    value = _num(value)
    if value is None:
        return '-'
    if currency == 'USD':
        return f'{value:,.2f} USD'
    return f'{int(value.to_integral_value()):,}원'


def _unit(total, count):
    total, count = _num(total), _num(count)
    if total is None or not count:
        return None
    return total / count


def regulation_excerpts(sources, fetch=None):
    """인용된 규정 조각에서 쪽수별 첫 문장 발췌를 읽습니다. 읽지 못하면 빈 목록입니다."""
    ids, pages = [], {}
    for source in sources or []:
        if source.get('chunk_id') and source['chunk_id'] not in pages:
            ids.append(source['chunk_id'])
            pages[source['chunk_id']] = ', '.join(map(str, source.get('pdf_pages', [])))
    if not ids:
        return []
    try:
        if fetch is None:
            from app.rag.vector_store import ChromaVectorStore
            fetch = ChromaVectorStore().fetch
        found = fetch(ids)
    except Exception:
        return []
    excerpts, seen = [], set()
    for identifier in ids:
        text = ' '.join((found.get(identifier, ('', {}))[0] or '').split())
        if len(text) < 20:
            continue
        text = text[:EXCERPT_CHARS].rstrip() + ('…' if len(text) > EXCERPT_CHARS else '')
        if text in seen:
            continue
        seen.add(text)
        excerpts.append(f'- {pages[identifier]}쪽: "{text}"')
        if len(excerpts) >= EXCERPT_LIMIT:
            break
    return excerpts


TRANSPORT_LABEL = {'public_transport': '대중교통', 'private_car': '자가용', 'company_car': '회사 제공 차량', 'rental_car': '대여 차량'}


def review_answer(context, review, fetch=None):
    """자동 계산이 불가능한 조건이면 이유·입력값·바꿔 볼 수 있는 조건을 안내합니다."""
    trip = review.get('input') or {}
    message = review.get('message') or '자동 계산에 추가 확인이 필요합니다.'
    lines = ['입력하신 조건은 **자동으로 금액을 확정할 수 없어** 담당자 확인이 필요합니다.', '', '**{확인 필요}**', '- ' + message]
    if trip:
        parts = [f"{TRIP_LABEL.get(trip.get('trip_type'), '')} 출장 · {trip.get('destination_city', '')}".strip(' ·'),
                 f"{trip.get('start_date')} ~ {trip.get('end_date')}"]
        if trip.get('distance_km') is not None:
            parts.append(f"왕복 {trip['distance_km']}km")
        if trip.get('same_city') is not None:
            parts.append('근무지와 동일 시·군' if trip['same_city'] else '근무지와 다른 시·군')
        if trip.get('lodging_nights') is not None:
            parts.append(f"숙박 {trip['lodging_nights']}박")
        parts.append(TRANSPORT_LABEL.get(trip.get('transport_mode'), '교통수단 미지정'))
        lines.extend(['', '**{입력하신 조건}**', '- ' + ' · '.join(parts)])
    tips = []
    if '근거리' in message or '50km' in message:
        tips.append('근거리 정액(별표3)은 숙박 없는 당일 출장에만 적용됩니다: 10km 미만 20,000원, 25km 미만 30,000원, 그 외 40,000원(교통비·일비·식비 포함).')
        tips.append('근무지와 다른 시·군이고 왕복 50km 이상이면 일비·식비·숙박비·교통비를 합산하는 일반 계산이 가능합니다. 거리와 동일 시·군 여부를 다시 확인해 보세요.')
    if tips:
        lines.extend(['', '**{안내}**', *('- ' + tip for tip in tips)])
    excerpts = regulation_excerpts(review.get('sources'), fetch)
    if excerpts:
        lines.extend(['', '**{관련 규정}**', *excerpts])
    lines.extend(['', '**{참고 문서}**', '- 여비규정(2025년도 07월 개정).pdf · 8, 16쪽'])
    context.answer_coverage = 'missing'
    return '\n'.join(lines)


def travel_estimate_answer(context, fetch=None):
    review = next((r.data['travel_expense'] for r in context.tool_results
                   if r.data.get('travel_expense') and r.data['travel_expense'].get('status') == 'needs_review'), None)
    if review is not None:
        return review_answer(context, review, fetch)
    calculation = next((r.data['travel_expense'] for r in context.tool_results
                        if r.data.get('travel_expense') and r.data['travel_expense'].get('status') in {'success', 'partial'}), None)
    if calculation is None:
        return None
    data = calculation['data']
    currency = data.get('allowance_currency', 'KRW')
    total = data.get('estimated_total_krw')
    days, nights, meal_days = data.get('days'), data.get('lodging_nights'), data.get('meal_days')
    overseas = data.get('trip_type') == 'overseas'
    missing = data.get('missing_inputs', [])
    known = data.get('known_subtotal_krw')
    if total is not None:
        headline = f"예상 출장비는 **{_fmt(total, 'KRW')}**입니다."
    elif known is not None:
        headline = f"교통비를 제외한 예상 출장비는 **{_fmt(known, 'KRW')}**입니다. 교통비를 입력하면 총액이 계산됩니다."
    elif data.get('known_allowances_subtotal') is not None:
        headline = (f"일비·식비·숙박비 합계는 **{_fmt(data['known_allowances_subtotal'], 'USD')}**입니다. "
                    '원화 총액은 교통비와 환율을 입력하면 계산됩니다.')
    else:
        headline = '일부 비용만 계산했습니다.'
    lines = [headline, '', '**{계산 내역}**']
    daily_unit, meal_unit = _unit(data.get('daily_allowance'), days), _unit(data.get('meal_allowance'), meal_days)
    lines.append(f"- 일비: {_fmt(daily_unit, currency)} × {days}일 = {_fmt(data.get('daily_allowance'), currency)}"
                 if daily_unit is not None else f"- 일비: {_fmt(data.get('daily_allowance'), currency)}")
    lines.append(f"- 식비: {_fmt(meal_unit, currency)} × {meal_days}일 = {_fmt(data.get('meal_allowance'), currency)}"
                 if meal_unit is not None else f"- 식비: {_fmt(data.get('meal_allowance'), currency)}")
    lodging = _num(data.get('lodging_budget'))
    if lodging is not None and nights:
        text = f"- 숙박비: {_fmt(_unit(lodging, nights), currency)} × {nights}박 = {_fmt(lodging, currency)}"
        cap = data.get('lodging_cap_per_night')
        if cap is not None:
            text += f" (1박 인정 상한 {_fmt(cap, currency)}"
            if data.get('lodging_basis') == 'ceiling_budget':
                text += ', 1박 단가가 없어 상한액으로 계산)'
            elif any('넘는' in note for note in data.get('notes', [])):
                text += ', 입력 단가가 상한을 넘어 상한 적용)'
            else:
                text += ' 이내)'
        lines.append(text)
    elif lodging is not None:
        lines.append(f"- 숙박비: {_fmt(lodging, currency)}")
    transport = data.get('transport_cost_krw')
    estimated = any('교통비(추정)' in note for note in calculation.get('assumptions', []))
    lines.append(f"- 교통비: {_fmt(transport, 'KRW')} ({'추정값, 아래 가정 참고' if estimated else '입력값'})" if transport is not None else '- 교통비: 입력되지 않아 합계에서 제외했습니다.')
    if _num(data.get('toll_cost_krw')):
        toll_estimated = any('통행료(추정)' in note for note in calculation.get('assumptions', []))
        lines.append(f"- 통행료: {_fmt(data['toll_cost_krw'], 'KRW')}" + (' (추정값)' if toll_estimated else ''))
    if overseas:
        rate = data.get('exchange_rate_krw_per_usd')
        lines.append(f"- 국외 수당·숙박 소계: {_fmt(data.get('known_allowances_subtotal'), 'USD')}"
                     + (f" × 환율 {rate}원/USD" if rate else ''))
    elif data.get('known_allowances_subtotal') is not None:
        lines.append(f"- 일비·식비·숙박비 소계: {_fmt(data['known_allowances_subtotal'], 'KRW')}")
    lines.append(f"- 합계: **{_fmt(total, 'KRW')}**" if total is not None else
                 f"- 확인된 소계: **{_fmt(data.get('known_subtotal_krw'), 'KRW')}**" if data.get('known_subtotal_krw') is not None
                 else '- 합계: 추가 입력 후 계산')
    conditions = [f"{TRIP_LABEL.get(data.get('trip_type'), '')} 출장 · {data.get('destination_city', '')}".strip(' ·'),
                  f"{data.get('start_date')} ~ {data.get('end_date')} ({days}일)",
                  f"숙박 {nights}박 · 식비 {meal_days}일"]
    if data.get('travel_grade'):
        conditions.append(f"적용 여비 등급 {data['travel_grade']}")
    if data.get('overseas_region_grade'):
        conditions.append(f"국외 지역 등급 {data['overseas_region_grade']}")
    lines.extend(['', '**{적용 조건}**', '- ' + ' · '.join(conditions)])
    excerpts = regulation_excerpts(calculation.get('sources') or data.get('sources'), fetch)
    if excerpts:
        lines.extend(['', '**{관련 규정}**', *excerpts])
    labels = {'transport_cost_krw': '교통비 예정 금액', 'exchange_rate_krw_per_usd': '품의일 기준 원/달러 환율',
              'lodging_cost_per_night': '숙박 예상 1박 단가', 'lodging_nights': '숙박 밤 수', 'meal_days': '식비 지급 일수'}
    notes = list(calculation.get('assumptions', []))
    notes += [f"입력이 더 필요합니다: {', '.join(labels.get(k, k) for k in data.get('missing_inputs', []))}"] if data.get('missing_inputs') else []
    notes.extend(data.get('notes', []))
    if notes:
        lines.extend(['', '**{확인 필요}**', *('- ' + note for note in notes)])
    lines.extend(['', '**{안내}**', '- 가정 계산이며 실제 지급·정산 확정액이 아닙니다.'])
    unique = []
    for source in calculation.get('sources') or data.get('sources', []):
        label = source['source'] + ' · ' + ', '.join(map(str, source['pdf_pages'])) + '쪽'
        if label not in unique:
            unique.append(label)
    if unique:
        lines.extend(['', '**{참고 문서}**', *('- ' + label for label in unique)])
    context.answer_coverage = 'partial' if calculation['status'] == 'partial' else 'direct'
    return '\n'.join(lines)
