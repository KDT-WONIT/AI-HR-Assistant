"""검증된 계산값과 개인 문의 기록을 모델이 변형하지 않도록 표시합니다."""
from decimal import Decimal


def amount(value):
    return f'{Decimal(str(value)):,.2f}'


def structured_answer(context):
    for result in context.tool_results:
        if 'inquiry_history' in result.data:
            record=result.data['inquiry_history']
            if record['status']!='success':
                context.answer_coverage='missing'
                return record.get('error',{}).get('message','문의 이력을 조회하지 못했습니다.')
            data=record['data']
            context.answer_coverage='direct'
            if not data['count']:
                return '본인 사번으로 저장된 관련 문의 이력이 없습니다.'
            lines=[f"본인의 이전 문의 {data['count']}건을 찾았습니다."]
            for index,item in enumerate(data['results'],1):
                lines.extend([f"\n{index}. {item['created_at']} · {item['category'] or '분류 없음'}",
                              f"질문: {str(item['question'])[:400]}",f"답변: {str(item['answer'] or '')[:700]}"])
            lines.extend(['\n[조회 근거] 본인 사번의 저장된 대화 기록','과거 답변은 현재 규정과 다시 대조해주세요.'])
            return '\n'.join(lines)
        if 'travel_expense' not in result.data:
            continue
        calculation=result.data['travel_expense']
        if calculation['status'] in {'error','needs_review'}:
            context.answer_coverage='missing'
            return calculation.get('message') or calculation.get('error',{}).get('message','여비 계산에 추가 확인이 필요합니다.')
        data=calculation['data']
        total=data.get('estimated_total_krw')
        context.answer_coverage='partial' if calculation['status']=='partial' else 'direct'
        lines=[f'예상 출장비는 {amount(total)}원입니다.' if total is not None else '일부 비용은 계산했지만 총액 계산에 추가 입력이 필요합니다.']
        labels={'daily_allowance':'일비','meal_allowance':'식비','lodging_budget':'숙박 예산',
                'transport_cost_krw':'교통비 예상액','toll_cost_krw':'통행료','known_subtotal_krw':'확인된 원화 소계'}
        for key,label in labels.items():
            value=data.get(key)
            if value is not None:
                unit='원' if key in {'transport_cost_krw','toll_cost_krw','known_subtotal_krw'} else data.get('allowance_currency',data.get('currency','KRW'))
                lines.append(f'- {label}: {amount(value)} {unit}')
        if data.get('missing_inputs'):
            labels.update({'exchange_rate_krw_per_usd':'품의일 기준 원/달러 환율','lodging_cost_per_night':'숙박 예상 단가'})
            lines.append('추가 입력: '+', '.join(labels.get(key,key) for key in data['missing_inputs']))
        lines.extend('- '+note for note in data.get('notes',[]))
        lines.append('\n가정 계산이며 실제 지급·정산 확정액이 아닙니다.')
        sources=calculation.get('sources') or data.get('sources',[])
        if sources:
            lines.append('\n[참고 문서]')
            unique=[]
            for source in sources:
                label=source['source']+' · '+', '.join(map(str,source['pdf_pages']))+'쪽'
                if label not in unique:
                    unique.append(label)
            lines.extend('- '+label for label in unique)
        return '\n'.join(lines)
    return None
