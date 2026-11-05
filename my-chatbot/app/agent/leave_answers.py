"""검색된 휴가 표의 기본·예외 일수와 신청 필수 단계를 정확히 표시합니다."""
import re

from app.agent.followups import current_question
from app.rag.retrieval import procedure_question


def spouse_leave_answer(context):
    if '배우자' not in context.question or '출산' not in context.question:
        return None
    question = current_question(context.question)
    days_question = bool(re.search(r'며칠|몇\s*일|일수', question))
    procedure = procedure_question(question)
    if not days_question and not procedure:
        return None
    from app.agent.answers import build_evidence, reference_block
    evidence = build_evidence(context)
    used, body = [], []
    def add(text, item):
        body.append(text)
        used.append((item.source, item.text))
    if days_question:
        table = next((item for item in evidence if '배우자 출산' in item.text and re.search(r'휴가일\s*\d+일\s*\(\d+일\)',item.text)),None)
        if table is None:
            return None
        basic, multiple = re.search(r'휴가일\s*(\d+)일\s*\((\d+)일\)',table.text).groups()
        # 자녀 순서(둘째)와 동시 출생 수(다태아)는 별개입니다.
        multiple_birth = bool(re.search(r'쌍둥|다태아|한\s*번에\s*(?:둘|2|셋|3)', context.question))
        chosen = multiple if multiple_birth else basic
        summary = f'말씀하신 배우자 출산 경조휴가는 {chosen}일입니다.'
        add(f'기본 휴가일수는 {basic}일이며, 한 번에 둘 이상의 자녀를 출산하는 경우에만 {multiple}일이 적용됩니다.',table)
        period = next((item for item in evidence if re.search(r'출산예정일\s*\d+일\s*전부터',item.text)),None)
        if period:
            match = re.search(r'출산예정일\s*(\d+)일\s*전부터\s*(\d+)일\s*내.*?(\d+)회',period.text)
            if match:
                before, within, count = match.groups()
                add(f'규정상 배우자 출산예정일 {before}일 전부터 {within}일 내 범위에서, {count}회에 한정해 나누어 사용할 수 있습니다.',period)
        holiday = next((item for item in evidence if '경조휴가' in item.text and '토요일' in item.text and '산입하지' in item.text),None)
        if holiday:
            add('토요일과 법정·약정휴일은 경조휴가 일수에 포함하지 않습니다.',holiday)
        context.answer_coverage = 'direct'
    else:
        common = next((item for item in evidence if all(word in item.text for word in ('각종 근태계','전산시스템','전자결재'))),None)
        approval = next((item for item in evidence if '특별유급휴가' in item.text and '사전에 소속 부서장의 허가' in item.text),None)
        proof = next((item for item in evidence if '증명할 서류를 첨부' in item.text and '제21조' in item.text),None)
        if not any((common,approval,proof)):
            return None
        summary = '배우자 출산휴가는 근태계를 제출하고 사전 허가를 받는 절차로 신청합니다.' if common and approval else '검색된 공통 휴가 신청 기준은 다음과 같습니다.'
        if common:
            add('공통 근태계 제출 기준에 따라 전산시스템 양식으로 작성해 전자결재 승인을 받습니다.',common)
        if proof:
            add('특별유급휴가를 요청할 때는 사유를 증명하는 서류를 첨부해야 합니다.',proof)
        if approval:
            add('휴가 사용 전에 소속 부서장의 허가를 받아야 합니다.',approval)
        proxy = next((item for item in evidence if '소속 부서원이 대리로 제출' in item.text),None)
        if proxy:
            add('특별한 사정으로 직접 제출하기 어려우면 소속 부서원이 대리 제출할 수 있습니다.',proxy)
        context.answer_coverage = 'partial'
    parts = [summary, '확인된 내용\n'+'\n'.join('- '+text for text in body), reference_block(used)]
    if procedure:
        parts.append('추가 안내\n시스템의 실제 메뉴명, 구체적인 증빙 종류와 사전 신청 기한은 담당 부서에 확인해주세요.')
    return '\n\n'.join(parts)


def leave_chain_answer(context):
    question = current_question(context.question)
    if '연차' not in question or not re.search(r'연달아|이어서|연속', question):
        return None
    from app.agent.answers import build_evidence, reference_block
    evidence = build_evidence(context)
    right = next((item for item in evidence if '연차유급휴가는 직원의 자유의사' in item.text),None)
    if right is None:
        return None
    # 연속 사용을 직접 정한 조항이 검색되면 모델이 그 조항을 설명하도록 넘깁니다.
    if any(re.search(r'연속\s*사용|연달아', item.text) for item in evidence):
        return None
    context.answer_coverage = 'partial'
    body = ['- 규정은 연차유급휴가를 직원의 자유의사에 따라 적절히 사용할 수 있도록 정하고 있습니다.']
    for result in context.tool_results:
        balance = result.data.get('leave_balance')
        if balance:
            body.append(f"- 연차 원장 기준 부여 {balance['granted_days']:g}일, 사용 {balance['used_days']:g}일로 잔여 연차는 {balance['remaining_days']:g}일입니다.")
    return '\n\n'.join([
        '경조휴가에 이어 연차를 쓰는 일정은 사전 확인이 필요합니다. 검색된 규정만으로 연속 사용이 승인되었다고 확정할 수는 없습니다.',
        '확인된 내용\n'+'\n'.join(body),reference_block([(right.source,right.text)]),
        '다음 단계\n경조휴가 종료일과 연차 사용 희망일을 함께 제시하여 소속 부서에 사용 일정을 확인해주세요.',
    ])


def _days(value) -> str:
    return f'{float(value):g}일'


def _md(date: str) -> str:
    return f'{int(date[5:7])}/{int(date[8:10])}'


def leave_balance_answer(context):
    """내 연차 잔여·사용 질문은 DB 값으로 계산 과정까지 보여줍니다(모델이 숫자를 만들지 않습니다)."""
    from app.integrations.leave_balance import balance_only_question
    data = next((result.data for result in context.tool_results if result.data.get('leave_balance')), None)
    if data is None or not balance_only_question(context.question):
        return None
    item = data['leave_balance']
    lines = [f"{item['year']}년 잔여 연차는 **{_days(item['remaining_days'])}**입니다.", '', '**{계산 내역}**',
             f"- 기본 부여: {_days(item['base_days'])}"]
    if item['carryover_days']:
        lines.append(f"- 이월: +{_days(item['carryover_days'])}")
    if item['adjusted_days']:
        sign = '+' if item['adjusted_days'] > 0 else '-'
        lines.append(f"- 조정(정산): {sign}{_days(abs(item['adjusted_days']))}")
    lines.extend([f"- 총 부여: {_days(item['granted_days'])}", f"- 사용 완료: -{_days(item['used_days'])}",
                  f"- 잔여: **{_days(item['remaining_days'])}**"])
    scheduled = item['scheduled_days'] + item['pending_days']
    if item['upcoming']:
        lines.extend(['', '**{예정·결재 중}**'])
        for entry in item['upcoming'][:5]:
            label = '승인' if entry['status'] == 'APPROVED' else '결재 중'
            lines.append(f"- {_md(entry['start_date'])} {entry['leave_type']} {_days(entry['days'])} ({label})")
        lines.append(f"- 예정분({_days(scheduled)})을 모두 사용하면 잔여 연차는 {_days(item['remaining_after_scheduled_days'])}이 됩니다.")
    if item['recent_used']:
        lines.extend(['', '**{최근 사용 내역}**'])
        lines.extend(f"- {_md(entry['start_date'])} {entry['leave_type']} {_days(entry['days'])}" for entry in item['recent_used'])
    projection = data.get('leave_projection')
    if projection:
        lines.extend(['', '**{사용 계획 반영}**',
                      f"- {_days(projection['requested_days'])}를 사용하면 잔여 {_days(projection['projected_remaining_days'])}"
                      + ('' if projection['sufficient'] else ' (잔여 연차가 부족합니다)')])
    lines.extend(['', '**{안내}**', f"- 기준: 사원 연차 원장({item['updated_at'][:10]} 갱신). 연차·반차·반반차만 사용으로 계산하며 경조휴가·공가는 차감하지 않습니다.",
                  '- 신청·승인 처리 중인 건은 인사 시스템에서 최종 확인해주세요.'])
    context.answer_coverage = 'direct'
    return '\n'.join(lines)

