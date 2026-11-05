"""복명서 제출 기한을 출장비 입금일로 오해하지 않도록 구분합니다."""
import re
from app.agent.followups import current_question


def travel_payment_answer(context):
    current = current_question(context.question)
    if not re.search(r'출장비|여비', current) or not re.search(r'언제|지급일|입금|예정일', current):
        return None
    from app.agent.answers import build_evidence, reference_block
    evidence = build_evidence(context)
    # 실제 입금 시점에 관한 조항이 있으면 정형 안내로 가리지 않습니다.
    if any(re.search(r'입금일|지급예정일|지급일은|매월\s*\d+일.*지급', item.text) for item in evidence):
        return None
    report = next((item for item in evidence if '국내출장자' in item.text and '복명서' in item.text and re.search(r'\d+일 이내',item.text)),None)
    if report is None:
        return None
    days = re.search(r'(\d+)일 이내',report.text)[1]
    body = [f'- 국내출장자는 근무지로 복귀한 후 {days}일 이내에 교통수단 이용 증명서와 숙박비 증명서를 첨부해 복명서를 제출해야 합니다.',
            '- 이 기한은 복명서 제출 기한이며 계좌 입금 예정일을 뜻하지 않습니다.']
    used = [(report.source,report.text)]
    means = next((item for item in evidence if '여비는 현금' in item.text and '법인카드' in item.text),None)
    if means:
        body.append('- 여비는 현금 지급이 원칙이며 교통비(근거리·전근여비 제외)와 숙박비는 법인카드를 사용하도록 정하고 있습니다.')
        used.append((means.source,means.text))
    context.answer_coverage = 'partial'
    return '\n\n'.join(['실제 출장비 입금일은 검색된 규정에서 확인할 수 없습니다.',
                          '확인된 내용\n'+'\n'.join(body),reference_block(used),
                          '다음 단계\n출장 후 휴가를 이어 사용하는 경우의 복명서 제출 시점과 실제 지급 예정일을 여비 정산 담당자에게 확인해주세요.'])
