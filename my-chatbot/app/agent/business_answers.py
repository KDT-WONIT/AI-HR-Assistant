"""검증된 계산값과 개인 문의 기록을 모델이 변형하지 않도록 표시합니다."""
from decimal import Decimal


def amount(value):
    return f'{Decimal(str(value)):,.2f}'


def structured_answer(context):
    from app.agent.leave_answers import spouse_leave_answer, leave_chain_answer
    from app.agent.travel_answers import travel_payment_answer
    from app.agent.leave_answers import leave_balance_answer
    from app.agent.travel_calc_answers import travel_calc_answer
    leave = (spouse_leave_answer(context) or leave_chain_answer(context) or travel_payment_answer(context)
             or leave_balance_answer(context) or travel_calc_answer(context))
    if leave is not None:
        return leave
    from app.agent.travel_estimate_answers import travel_estimate_answer
    estimate = travel_estimate_answer(context)
    if estimate is not None:
        return estimate
    for result in context.tool_results:
        info = result.data.get('tenure')
        if info:
            context.answer_coverage = 'direct'
            who = '현재' if info.get('is_self') else f"{info.get('name')} 님은 현재"
            span = f"{info['years']}년 {info['months']}개월" if info['years'] else f"{info['months']}개월"
            return (f"{who} 입사 {info['year_rank']}년차입니다.\n"
                    f"입사일 {info['hired_at']} 기준으로 오늘까지 {span} 근무하셨습니다(입사 첫해를 1년차로 계산).\n"
                    f"\n[조회 근거] 사원 정보의 입사일")
        if result.data.get('user_situation'):
            context.answer_coverage = 'direct'
            return '말씀하신 상황을 이번 대화에서 참고하겠습니다. 이어서 궁금한 휴가·지원금·출장비를 물어봐 주세요.'
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
