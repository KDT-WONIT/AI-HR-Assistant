"""질문의 생활 표현을 규정 표현으로 확장하고 결과를 함께 순위화합니다."""

import re

from app.schemas import Source


def procedure_question(question: str) -> bool:
    return bool(re.search(r'(신청|제출|정산|등록).*(방법|절차|어떻게|어디|해야|하나요)|'
                          r'(어떻게|어디서|어디에).*(신청|제출|정산|등록)|며칠\s*전|신청\s*기한',question))


def search_queries(question: str) -> list[str]:
    if not procedure_question(question):
        return [question]
    if any(word in question for word in ('연차','휴가','반차','근태')):
        return [question, '휴가 근태계 제출 전산시스템 양식 전자결재 승인 신청 방법',
                '연차유급휴가 청구 사용 시기 사용 단위']
    return [question, question + ' 신청서 제출 승인 신청 절차 처리 방법']


def rank_sources(question: str, groups: list[list[Source]], limit: int) -> list[Source]:
    scores = {}
    items = {}
    for group in groups:
        seen = set()
        for rank,source in enumerate(group):
            key = source.chunk_id or source.document + ':' + source.text
            if key in seen:
                continue
            seen.add(key)
            scores[key] = scores.get(key,0) + 1/(40+rank)
            items.setdefault(key,source)
    if procedure_question(question):
        for key,source in items.items():
            text = source.text
            if '연차' in question:
                if '각종 근태계' in text and any(word in text for word in ('전자결재','제출','전산시스템')):
                    scores[key] += 0.10
                elif '연차' in text and any(word in text for word in ('청구','반일','반반일','사용 시기')):
                    scores[key] += 0.025
            if '개정일자' in text and '변 경 내 용' in text:
                scores[key] -= 1  # 개정 이력 표는 현재 운영 절차의 근거로 우선하지 않습니다.
    return [items[key] for key in sorted(scores,key=scores.get,reverse=True)[:limit]]
