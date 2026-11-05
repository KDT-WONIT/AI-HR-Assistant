"""출장비 계산기 결과를 계산 과정과 함께 보여줍니다. 숫자는 코드가 계산하며 모델이 만들지 않습니다."""


def travel_calc_answer(context):
    data = next((result.data['travel_calc'] for result in context.tool_results if result.data.get('travel_calc')), None)
    if data is None:
        return None
    won = lambda value: f'{int(value):,}원'
    units = data['daily_units']
    day_text = f"{data['days']}일" if units == data['days'] else f'{units:g}일분'
    lines = [f"예상 출장비는 **{won(data['total'])}**입니다.", '', '**{계산 내역}**',
             f"- 일비: {won(data['daily_rate'])} × {day_text} = {won(data['allowance'])}",
             f"- 식비: {won(data['meal_rate'])} × {data['days']}일"
             + (f" ({data['meal_note']})" if data['meal_note'] else '') + f" = {won(data['meals'])}",
             f"- 숙박비: {won(data['lodging_per_night'])} × {data['nights']}박 = {won(data['lodging'])}",
             f"- 교통비: {won(data['transport_cost'])} (입력값)", f"- 합계: **{won(data['total'])}**", '',
             '**{입력하신 조건}**',
             f"- 출장 {data['days']}일 · 숙박 {data['nights']}박 · 교통비 {won(data['transport_cost'])} · 1박 숙박비 {won(data['lodging_per_night'])}"]
    if data['lodging_note']:
        lines.extend(['', '**{확인 필요}**', '- ' + data['lodging_note']])
    lines.extend(['', '**{안내}**',
                  '- 국내 출장 기준의 가정 계산이며 실제 지급·정산 확정액이 아닙니다. 교통비와 숙박비는 증빙을 기준으로 정산됩니다.',
                  '- 조건을 바꿔 다시 계산하려면 "3일 출장 2박 교통비 12만원 1박 9만원"처럼 새 값을 알려주세요.',
                  '', '**{참고 문서}**', f"- {data['source']} · {data['source_pages']} · 일비·식비·숙박비 지급 기준"])
    context.answer_coverage = 'direct'
    return '\n'.join(lines)
