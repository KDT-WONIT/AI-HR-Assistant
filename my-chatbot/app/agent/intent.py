"""툴콜링 보조 기준: 인사말·잡담은 업무 도구가 아닌 일반 대화로 보냅니다.

AI 라우터(모델)가 '안녕하세요' 같은 질문을 업무 도구로 보내면 규정 검색 결과만 나열되므로,
코드로 확인할 수 있는 기준을 라우터 앞뒤에 둡니다.
  1) 라우터 앞: 인사·감사·작별·자기소개 질문 등 분명한 잡담이면 일반 대화로 바로 보냅니다.
  2) 라우터 뒤: 업무 관련 단어가 전혀 없고 도구가 가져온 계산·조회 데이터도 없으면 일반 대화로 돌립니다.
"""
import re

GENERAL_TOOL_ID = 'general'

# 사내 업무 질문으로 볼 수 있는 단어(한 개라도 있으면 업무 질문으로 취급해 라우터 판단을 존중합니다).
BUSINESS_TERMS = (
    '규정', '규칙', '지침', '세칙', '기준', '절차', '신청', '승인', '결재', '서류', '양식', '지원', '지급', '청구',
    '연차', '휴가', '반차', '휴직', '복직', '병가', '경조', '출산', '육아', '근무', '근태', '야근', '초과', '당직', '재택', '유연',
    '급여', '월급', '연봉', '임금', '수당', '상여', '성과급', '보너스', '퇴직', '퇴사', '입사', '채용', '승진', '평가', '인사', '발령', '징계', '교육', '연수',
    '복리', '복지', '학자금', '대출', '사택', '주택', '건강검진', '보험', '식대', '통근', '동호회', '사내',
    '출장', '여비', '숙박', '교통비', '항공', '비용', '정산', '영수증', '법인카드', '구매', '계약', '발주', '예산', '회계', '세금',
    '보안', '정보보호', '개인정보', '유출', '반출', '비밀', '안전', '사고', '재해', '품질', '연구', '개발', '특허', '기술', '사업', '윤리', '청렴', '부패', '감사', '신고', '준법', '법무', '노조', '노사',
    '담당자', '연락처', '내선', '전화', '이메일', '사번', '부서', '팀', '직급', '직책', '직원', '사원', '조직', '문의', '이력', '시설', '사무', '주차', '회의실',
    '회사', '업무', '직장', '상사', '동료',
)

CHITCHAT = re.compile(
    r'^\s*(안녕|하이|헬로|hello|hi\b|hey\b|반가|처음\s*뵙|좋은\s*(아침|하루|저녁)|고마워|고맙|감사|땡큐|thanks?|수고|잘\s*가|잘\s*있|바이|bye|'
    r'ㅎㅇ|ㅋㅋ|ㅎㅎ|ㅇㅋ|네\s*$|응\s*$|알겠|오케이|ok\b)', re.I)
ABOUT_BOT = re.compile(r'(너|넌|당신|챗봇|도우미).{0,8}(누구|뭐|무엇|이름|할\s*수|도와|어떤)|(자기\s*소개|뭘?\s*할\s*수\s*있)')


def looks_business(question: str) -> bool:
    return any(term in question for term in BUSINESS_TERMS)


def is_chitchat(question: str) -> bool:
    """분명한 인사·감사·잡담·챗봇 소개 질문이면 참. 업무 단어가 섞여 있으면 거짓입니다."""
    from app.agent.followups import current_question
    text = current_question(question).strip()
    if not text or looks_business(text):
        return False
    return bool(CHITCHAT.search(text) or ABOUT_BOT.search(text))


STRUCTURED_KEYS = ('inquiry_history', 'travel_expense', 'travel_calc', 'calculator', 'user_situation', 'leave_balance',
                   'leave_entitlement', 'leave_projection', 'employee', 'hr_contacts', 'departments')


def should_fall_back_to_general(question: str, data: dict, history_has_business: bool = False) -> bool:
    """도구 실행 뒤에도 업무 질문으로 볼 근거가 없으면 참(= 일반 대화로 답해야 함)."""
    from app.agent.followups import current_question
    text = current_question(question)
    if looks_business(text) or history_has_business:
        return False
    return not any(data.get(key) for key in STRUCTURED_KEYS)
