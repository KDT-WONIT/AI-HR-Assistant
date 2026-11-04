"""연봉·급여 금액 질문에서 규정 표의 핵심 행을 서버가 직접 정리해 보여줍니다.

작은 로컬 모델은 표를 일반론("직위와 등급에 따라 결정됩니다")으로 요약하기 쉽습니다.
표를 복원한 출처(Source.highlights)에 사용자 직급의 행이 있으면, 모델 출력과 별개로 등급·금액·구분을
그대로 보여줍니다. 숫자는 문서에서 복원한 값이며 모델이 만들지 않습니다.
"""

import re

from app.rag.retrieval import focus_grades, pay_amount_question, personal_pay_question
from app.schemas import AnswerContext, Source

MAX_LINES = 12


def pages_label(source: Source) -> str:
    pages = sorted(source.pages or ([source.page] if source.page else []))
    if not pages:
        return ''
    return f'{pages[0]}쪽' if len(pages) == 1 else f'{pages[0]}~{pages[-1]}쪽'


def key_content_block(context: AnswerContext) -> str:
    if not pay_amount_question(context.question):
        return ''
    sources = [source for source in context.sources if source.highlights]
    if not sources:
        return ''
    profile = context.user_profile
    grades = focus_grades(context.question, profile.grade if profile else None)
    subject = ', '.join(grades) if grades else '해당 직급'
    owner = f'{profile.name}님({subject})' if profile and grades == [profile.grade] else subject
    lines, budget = [], MAX_LINES
    for source in sources:
        if budget <= 0:
            break
        head = ' · '.join(part for part in (source.document.removesuffix('.pdf'), pages_label(source), source.caption) if part)
        rows = source.highlights[:budget]
        lines.append('· ' + head)
        lines.extend('  - ' + row for row in rows)
        budget -= len(rows)
    if personal_pay_question(context.question):
        caution = ('※ 개인별 확정 연봉액(연봉등급·실지급액)은 현재 연결된 급여 자료에 없어 알 수 없습니다. '
                   '위 내용은 규정상의 지급 기준이며, 본인에게 적용되는 직위·등급과 실제 금액은 급여 담당 부서에 확인해주세요.')
    else:
        caution = '※ 규정상의 지급 기준입니다. 개인별로 적용되는 직위·등급은 급여 담당 부서에 확인해주세요.'
    return f'{owner} 기준으로 규정에서 확인되는 지급 기준\n' + '\n'.join(lines) + '\n' + caution


def add_key_content(context: AnswerContext, answer: str) -> str:
    """모델 답변에 핵심 지급 기준 블록을 끼워 넣습니다. 모델이 근거를 정리하지 못한 경우에도 표의 내용은 보여줍니다."""
    block = key_content_block(context)
    if not block:
        return answer
    paragraphs = answer.split('\n\n')
    if context.answer_coverage == 'missing':
        # 일반론조차 정리하지 못한 폴백 문구 대신 확인된 표 내용을 안내합니다.
        paragraphs = ['규정 문서에서 확인되는 핵심 내용을 정리했습니다.',
                      *[item for item in paragraphs[1:] if not item.startswith(('확인된 내용', '확인 범위'))]]
    position = next((index for index, item in enumerate(paragraphs)
                     if index > 0 and re.match(r'\[|추가 안내|다음 단계', item)), len(paragraphs))
    paragraphs.insert(position, block)
    if personal_pay_question(context.question) or context.answer_coverage == 'missing':
        context.answer_coverage = 'partial'  # 확정 금액은 알 수 없으므로 담당자 안내 대상으로 둡니다.
    return '\n\n'.join(paragraphs)
