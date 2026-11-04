"""질문에 직접 답하는 설명과 검증 가능한 문서 근거를 연결합니다."""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from app.schemas import AnswerContext, RequestModel, Source
from app.rag.retrieval import procedure_question


class GroundedPoint(RequestModel):
    text: str = Field(min_length=1, max_length=500)
    source_id: str
    evidence_id: str


class AnswerDraft(RequestModel):
    coverage: Literal['direct', 'partial', 'missing']
    summary: str = Field(min_length=1, max_length=600)
    points: list[GroundedPoint] = Field(max_length=6)


@dataclass(frozen=True)
class Evidence:
    id: str
    source_id: str
    source: Source
    text: str


def build_evidence(context: AnswerContext) -> list[Evidence]:
    """원문 문장에 서버가 ID를 붙입니다. 모델이 원문을 재복사하다 틀리는 문제를 피합니다."""
    evidence = []
    for index,source in enumerate(context.sources,1):
        header = source.document.split('(')[0].removesuffix('.pdf').strip()
        for line in source.text.splitlines():
            line = line.strip().removeprefix('- ').strip()
            if not line or line.startswith('문서:') or line == header or re.match(r'^제\d+[장절]\s',line):
                continue
            for sentence in re.split(r'(?<=[.!?])\s+(?=[가-힣①-⑳])',line):
                if sentence.strip():
                    evidence.append(Evidence(f'E{len(evidence)+1}',f'S{index}',source,sentence.strip()))
    return evidence


def is_supported(text: str, quotes: list[str], facts: list[str] | None = None) -> bool:
    """기본 원문/수치/부정 검사. 의미 전체의 사실성을 증명하는 검사는 아닙니다."""
    if not isinstance(text, str) or not text.strip() or not quotes:
        return False
    numbers = lambda value: set(re.findall(r'\d+(?:[.,]\d+)*', value.replace(',', '')))
    prose = re.sub(r'(?m)^\s*\d+[.)]\s*', '', text)
    if not numbers(prose).issubset(numbers('\n'.join(quotes + (facts or [])))):
        return False
    for name in re.findall(r'ERP|SAP|Workday|그룹웨어|포털',text,re.IGNORECASE):
        if name.lower() not in '\n'.join(quotes).lower():
            return False
    for scope in ('국내','해외'):
        if scope in text and scope not in '\n'.join(quotes):
            return False
    negative = r'제외|아니|않|없|금지|불가|못|지급하지|지원하지|제한|예외|어려|어렵|곤란'
    polarity_evidence = re.sub(r'제한\s*(?:없이|없음|없다|없습니다)','', '\n'.join(quotes))
    return not re.search(negative, polarity_evidence) or bool(re.search(negative, text))


def wants_procedure(question: str) -> bool:
    return procedure_question(question)


def quote_position(text: str, quote: str) -> int:
    positions = [index for index,char in enumerate(text) if not char.isspace()]
    compact = ''.join(text[index] for index in positions)
    offset = compact.find(re.sub(r'\s+','',quote))
    return positions[offset] if offset >= 0 and offset < len(positions) else -1


def relevant_to_question(question: str, quote: str, source: Source) -> bool:
    if '연차' not in question:
        return True
    position = quote_position(source.text,quote)
    before = source.text[:position] if position >= 0 else ''
    articles = list(re.finditer(r'제\d+조(?:의\d+)?\s*\([^\n)]+\)',before))
    article = articles[-1].group() if articles else (source.section or '')
    compact = re.sub(r'\s+','',quote + article)
    if '연차휴가로변경' in compact and any(word in quote for word in ('특별휴가','헌혈휴가','자녀돌봄','난임','휴직')):
        return False
    return '연차' in quote + article or '각종근태계' in compact or '근태계제출' in compact


def supports_procedure(question: str, quote: str, source: Source) -> bool:
    """일수·이월 조항을 신청 절차의 근거로 사용하는 것을 보수적으로 제한합니다."""
    if not re.search(r'신청|제출|승인|결재|등록|요청|보고|청구', quote):
        return False
    if not re.search(r'신청서|시스템|전자|포털|서면|제출|결재|승인.*받|\d+\s*일\s*전|까지|담당|청구.*시기', quote):
        return False
    return relevant_to_question(question,quote,source)


def citation(source: Source, quote: str = '') -> str:
    pages = source.pages or ([source.page] if source.page else [])
    parts = [source.document]
    if pages:
        parts.append(', '.join(map(str,pages)) + '쪽')
    position = quote_position(source.text,quote) if quote else -1
    text = source.text[:position + len(quote)] if position >= 0 else ''
    articles = re.findall(r'제\d+조(?:의\d+)?\s*\([^\n)]+\)', text)
    section = articles[-1] if articles else source.section
    if section:
        parts.append(section)
    return ' · '.join(parts)


def reference_block(items: list[tuple[Source,str]], label: str = '참고 문서') -> str:
    citations = list(dict.fromkeys(citation(source,quote) for source,quote in items))
    return f'[{label}]\n' + '\n'.join('- ' + item for item in citations)


def clean_text(text: str) -> str:
    # 내부 검색 ID는 직원용 답변에 노출하지 않습니다.
    text = re.sub(r'\s*[\[(][SE]\d+(?:\s*(?:참조|참고))?[\])]','',text).strip()
    return re.sub(r'^(?:신청 방법|전산시스템 양식 사용|대리 제출 가능|제출 방법)\s*[:：]\s*','',text)


def readable_fallback(context: AnswerContext, facts: list[str], *, procedure_missing: bool = False) -> str:
    context.answer_coverage = 'missing'
    if procedure_missing:
        summary = '검색된 규정에서는 질문하신 구체적인 신청 절차를 확인할 수 없습니다.'
        body = '확인 범위\n- 신청 시스템, 사전 신청 기한, 승인 경로를 안내할 직접 근거가 부족합니다.'
        next_step = '담당 인사 부서에 신청 경로와 제출 시점, 승인 절차를 확인해주세요.'
    else:
        summary = '검색된 자료만으로는 질문에 대한 답변을 확실하게 정리하기 어렵습니다.'
        body = '확인된 내용\n' + '\n'.join('- ' + item for item in facts) if facts else ''
        next_step = '대상이나 상황을 조금 더 구체적으로 알려주시거나 담당 부서에 확인해주세요.'
    parts = [summary, body]
    if context.sources:
        # 답변 근거로 확정한 문서와 단순히 검색된 문서를 구분합니다.
        parts.append(reference_block([(source,'') for source in context.sources[:2]],'검토한 문서 · 세부 답변 미확인'))
    parts.append('다음 단계\n' + next_step)
    return '\n\n'.join(part for part in parts if part)


MIN_BODY_POINTS, MAX_BODY_POINTS = 3, 5


def supplement_points(context: AnswerContext, chosen: list, body: list[str], summary: str) -> list[str]:
    """모델이 핵심 조건을 적게 골랐을 때, 같은 문서의 원문 문장 중 질문과 관련 깊은 것을 보충합니다.
    원문 문장 그대로라 근거 검증을 통과하며, 질문 단어와 겹치는 순서로 고릅니다."""
    if len(body) >= MIN_BODY_POINTS:
        return body
    used = {id(item.source) for _, item in chosen}
    already = {item.id for _, item in chosen}  # 모델이 이미 풀어 쓴 근거 문장은 원문 그대로 다시 붙이지 않습니다.
    terms = {word for word in re.findall(r'[가-힣A-Za-z0-9]{2,}', context.question) if word not in {'알려주세요', '알려줘', '어떻게', '무엇', '입니다'}}
    stems = {word[:-1] if len(word) > 2 else word for word in terms}
    taken = {re.sub(r'\s+', '', value) for value in [summary, *body]}
    candidates = []
    for item in build_evidence(context):
        text = clean_text(item.text)
        compact = re.sub(r'\s+', '', text)
        if item.id in already or id(item.source) not in used or not 12 <= len(text) <= 300 or text.startswith(('[', '|')):
            continue
        if any(compact in done or done in compact for done in taken) or re.fullmatch(r'[\d\s.,~\-]+', text):
            continue
        if not relevant_to_question(context.question, item.text, item.source):
            continue
        score = sum(1 for stem in stems if stem in text)
        if score:
            candidates.append((-score, len(candidates), text))
    for _, _, text in sorted(candidates):
        if len(body) >= MAX_BODY_POINTS:
            break
        body.append(text)
    return body


def render_answer(context: AnswerContext, draft: AnswerDraft, facts: list[str]) -> str:
    context.answer_coverage = 'missing'
    evidence = {item.id:item for item in build_evidence(context)}
    points = []
    for point in draft.points:
        item = evidence.get(point.evidence_id)
        if item is None or item.source_id != point.source_id:
            continue
        if not is_supported(clean_text(point.text),[item.text]):
            continue
        if not relevant_to_question(context.question,item.text,item.source):
            continue
        if '국내대학교' in item.text and '해외' not in item.text and '국내' not in point.text:
            point = point.model_copy(update={'text':'국내대학교의 경우, ' + clean_text(point.text)})
        elif '해외대학교' in item.text and '국내' not in item.text and '해외' not in point.text:
            point = point.model_copy(update={'text':'해외대학교의 경우, ' + clean_text(point.text)})
        points.append((point,item))
    if wants_procedure(context.question) and not points:
        return readable_fallback(context,facts,procedure_missing=True)
    if not points:
        return readable_fallback(context,facts)
    procedure = wants_procedure(context.question)
    direct_procedure = any(supports_procedure(context.question,item.text,item.source) for point,item in points)
    quotes = [item.text for point,item in points]
    summary = clean_text(draft.summary)
    if not is_supported(summary,quotes,facts):
        summary = clean_text(points[0][0].text)
    partial = draft.coverage != 'direct'
    common = next(((point,item) for point,item in points if '각종근태계' in re.sub(r'\s+','',item.text)),None)
    if procedure and not direct_procedure:
        summary = '신청에 참고할 수 있는 관련 규정은 다음과 같습니다.'
        partial = True
    elif procedure and common:
        summary = '공통 근태계 제출 기준에 따르면, ' + clean_text(common[0].text)
        text = common[1].text
        if all(word in text for word in ('전산시스템','양식','전자결재','승인')) and not re.search(r'않|아니|없|불필요|제외',text):
            # 같은 근거 문장 안의 필수 승인 단계를 축약 과정에서 빠뜨리지 않습니다.
            summary = '공통 근태계 제출 기준에 따라, 전산시스템의 양식으로 작성하고 전자결재 승인을 받으면 됩니다.'
        partial = True
    body = list(dict.fromkeys(clean_text(point.text) for point,source in points
                             if clean_text(point.text) != summary and not (procedure and common and point is common[0])))
    body.extend(item for item in facts if item not in body and item != summary)
    body = supplement_points(context, points, body, summary)
    parts = [summary]
    if body:
        parts.append('확인된 내용\n' + '\n'.join('- ' + item for item in body))
    parts.append(reference_block([(item.source,item.text) for point,item in points]))
    if partial:
        parts.append('추가 안내\n시스템의 구체적인 메뉴 경로나 사전 신청 기한은 위 근거만으로 확인되지 않으므로 담당 부서에 확인해주세요.'
                     if procedure else '추가 안내\n위 근거에서 확인되지 않은 세부사항은 담당 부서에 확인해주세요.')
    context.answer_coverage = 'partial' if partial else 'direct'
    return '\n\n'.join(parts)
