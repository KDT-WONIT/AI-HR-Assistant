"""메인 화면 출장 여비 계산기(전체 입력 폼) 결과를 계산 과정·규정과 함께 보여줍니다.

금액은 계산 도구가 만든 값만 사용하며 모델이 만들지 않습니다.
규정 발췌는 계산에 인용된 규정 조각 원문을 그대로 보여줍니다."""
from decimal import Decimal

EXCERPT_LIMIT = 3
EXCERPT_CHARS = 160
TRIP_LABEL = {'domestic': '국내', 'overseas': '국외'}


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
    lines.append(f"- 교통비: {_fmt(transport, 'KRW')} (입력값)" if transport is not None else '- 교통비: 입력되지 않아 합계에서 제외했습니다.')
    if _num(data.get('toll_cost_krw')):
        lines.append(f"- 통행료: {_fmt(data['toll_cost_krw'], 'KRW')}")
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
