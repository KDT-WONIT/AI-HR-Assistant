"""질문의 생활 표현을 규정 표현으로 확장하고 결과를 함께 순위화합니다."""

import re
from dataclasses import dataclass

from app.schemas import Source

PAY_TERMS = '연봉|월급|급여|보수|임금|봉급|성과급|상여'
AMOUNT = re.compile(r'\d{1,3}(?:,\d{3})+')


@dataclass(frozen=True)
class RetrievalHints:
    """질문한 사용자의 프로필에서 온 검색 보조 정보(표에서 본인에게 해당하는 행을 찾는 데 사용)."""
    grade: str | None = None
    job_title: str | None = None
    department: str | None = None
    location: str | None = None

    def focus_terms(self) -> list[str]:
        return [self.grade] if self.grade else []


def pay_amount_question(question: str) -> bool:
    """'연봉 얼마야'처럼 급여 금액·구성을 묻는 질문. '연봉 언제 오르지'(시점)는 해당하지 않습니다."""
    return bool(re.search(rf'(?:{PAY_TERMS}).{{0,12}}(?:얼마|금액|액수|수준|받|많|적|계산|산정|구성|어느\s*정도)|'
                          rf'(?:얼마|금액).{{0,8}}(?:{PAY_TERMS})', question))


def focus_grades(question: str, profile_grade: str | None = None) -> list[str]:
    """표에서 찾을 직급. 질문에 직급이 직접 나오면(예: '1직급 연봉') 그것을, 아니면 질문자의 직급을 씁니다."""
    explicit = list(dict.fromkeys(re.findall(r'\d직급(?:\([가나]\))?', question)))
    return explicit or ([profile_grade] if profile_grade else [])


def personal_pay_question(question: str) -> bool:
    return pay_amount_question(question) and bool(re.search(r'(?:^|\s)(?:나|내|제|저)(?:\s|의|가|는|도|$)', question))


def revision_history(text: str) -> bool:
    return bool(re.search(r'개정\s*일자', text) and re.search(r'개정\s*이력|변\s*경\s*내\s*용|개정\s*번호', text))


def procedure_question(question: str) -> bool:
    return bool(re.search(r'(신청|제출|정산|등록).*(방법|절차|어떻게|어디|해야|하나요)|'
                          r'(어떻게|어디서|어디에).*(신청|제출|정산|등록)|며칠\s*전|신청\s*기한',question))


def search_queries(question: str, hints: RetrievalHints | None = None) -> list[str]:
    if '출산' in question and re.search(r'지원금|경조금|경조사비|축하금|얼마|수당', question):
        return [question, '복리후생규정 출산축하금 둘째 자녀 지급 신청 증명서류',
                '출산축하금 지급액 공무원보수 업무지침 출산일 1년']
    if '배우자' in question and '출산' in question:
        if procedure_question(question):
            return [question, '휴가 각종 근태계 제출 전산시스템 전자결재 소속 부서장 허가',
                    '특별유급휴가 휴직 요청 사실을 증명할 서류 첨부',
                    '제22조 특별유급휴가 사전에 소속 부서장의 허가']
        return [question, '경조휴가의 종류 배우자 출산전후휴가 휴가일 별표',
                '배우자 출산전후휴가 휴무일 토요일 휴일 산입 소속 부서장 허가']
    if re.search(r'출장|여비', question) and re.search(r'언제|지급일|지급\s*시|입금|예정일', question):
        return [question, '여비의 지급 및 정산 현금 법인카드 복명서 근무지 복귀 7일 이내']
    if pay_amount_question(question):
        # 짧은 질문만으로는 표 조각이 검색되지 않으므로 직급과 규정 표현을 붙여 여러 각도로 찾습니다.
        grade = (hints.grade or '') if hints else ''
        return [question,
                f'{grade} 직원 연봉 구성 기본연봉 직무급 성과연봉 연봉월액 지급기준'.strip(),
                f'{grade} 직위 직무평가급 지급기준 등급 금액 월'.strip(),
                f'{grade} 기본연봉 등급 직급별 상한 하한 금액 별표'.strip()]
    if not procedure_question(question):
        return [question]
    if any(word in question for word in ('연차','휴가','반차','근태')):
        return [question, '휴가 근태계 제출 전산시스템 양식 전자결재 승인 신청 방법',
                '연차유급휴가 청구 사용 시기 사용 단위']
    return [question, question + ' 신청서 제출 승인 신청 절차 처리 방법']


def rank_sources(question: str, groups: list[list[Source]], limit: int,
                 hints: RetrievalHints | None = None) -> list[Source]:
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
    if pay_amount_question(question):
        grade = hints.grade if hints else None
        for key,source in items.items():
            text = source.text
            if revision_history(text):
                scores[key] -= 1  # 개정 이력 표에는 '기본연봉' 같은 단어만 있고 금액 근거가 없습니다.
            elif AMOUNT.search(text) and grade and grade in text:
                scores[key] += 0.05
            elif AMOUNT.search(text):
                scores[key] += 0.015
            if re.search(r'연봉.{0,4}(?:구성|산정)|기본연봉|직무급|연봉월액',text) and not revision_history(text):
                scores[key] += 0.01
            if '임원' in source.document and '임원' not in question:
                scores[key] -= 0.5  # 직원 본인의 연봉 질문에 임원 규정을 섞지 않습니다.
    if procedure_question(question):
        for key,source in items.items():
            text = source.text
            if any(word in question for word in ('연차', '휴가', '근태')):
                if '각종 근태계' in text and any(word in text for word in ('전자결재','제출','전산시스템')):
                    scores[key] += 0.10
                elif '연차' in text and any(word in text for word in ('청구','반일','반반일','사용 시기')):
                    scores[key] += 0.025
                if '특별유급휴가' in text and ('증명할 서류' in text or '사전에 소속 부서장의 허가' in text):
                    scores[key] += 0.06
            if '개정일자' in text and '변 경 내 용' in text:
                scores[key] -= 1  # 개정 이력 표는 현재 운영 절차의 근거로 우선하지 않습니다.
    for key, source in items.items():
        text = source.text
        if revision_history(text) or re.search(r'^부\s*칙', source.section or ''):
            scores[key] -= 0.2
        if '출산' in question and re.search(r'지원금|경조금|경조사비|축하금|수당', question):
            if re.search(r'출산(?:축하금|경조금)', re.sub(r'\s+', '', text)):
                scores[key] += 0.15
            if '행동강령' in source.document:
                scores[key] -= 0.5
        if '배우자' in question and '출산' in question:
            if '해외근무' in source.document and not any(word in question for word in ('해외', '국외')):
                scores[key] -= 0.5
            if '배우자 출산전후휴가' in text and '휴가일' in text:
                scores[key] += 0.1
            if any(word in text for word in ('유산', '사산')) and not any(word in question for word in ('유산', '사산')):
                scores[key] -= 0.08
    return [items[key] for key in sorted(scores,key=scores.get,reverse=True)[:limit]]
