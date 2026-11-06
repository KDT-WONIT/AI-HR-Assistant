"""도구가 가져온 데이터가 질문 의도와 맞는지 확인하는 안전망.

AI 라우터가 질문을 엉뚱한 도구로 보내거나, 도구가 단어 하나(예: '이메일')에 반응해 관련 없는 조회를 해도
'직원 목록' 같은 조회 결과가 규정 답변을 대신하지 못하도록 막습니다.
"""
import re

POLICY_CUE = re.compile(r'개인|외부|보내도|보내|써도|해도|되나요|되는지|가능|허용|금지|반출|유출|위반|보안|클라우드|규정|징계')
LOOKUP_CUE = re.compile(r'알려|주소|누구|뭐야|뭔가요|조회|찾|보여|번호')
OWN_INFO_WORDS = ('내 정보', '내정보', '내 부서', '내 직급', '입사일', '내 소속', '내 연락처', '내 이메일', '내 내선', '내 근무지')
PERSON_CUE = re.compile(r'정보|직급|부서|입사|소속|누구|직책|사번')
DEPARTMENT_WORDS = ('부서 목록', '조직도', '부서 조회', '부서 연락', '부서 위치', '부서 정보', '부서별 인원', '대표내선')
DIRECTORY_KEYS = ('employee', 'hr_contacts', 'departments')


def is_contact_lookup(question: str) -> bool:
    """사람·담당자 연락처를 찾는 질문만 참으로 판단합니다. '이메일'이 들어갔다는 이유만으로 직원 목록을 조회하지 않습니다."""
    if any(word in question for word in ('담당자', '부서 직원', '팀원')):
        return True
    if any(word in question for word in ('내선', '연락처', '전화번호')):
        return not (POLICY_CUE.search(question) and not LOOKUP_CUE.search(question))
    if '이메일' in question or '메일' in question:
        return bool(LOOKUP_CUE.search(question)) and not POLICY_CUE.search(question)
    return False


def directory_lookup_intent(question: str) -> bool:
    """질문이 사원·부서 정보를 직접 찾는 요청인지 판단합니다."""
    from app.agent.followups import current_question
    current = current_question(question)
    compact = current.replace(' ', '')
    if any(word in current for word in OWN_INFO_WORDS) or any(word.replace(' ', '') in compact for word in DEPARTMENT_WORDS):
        return True
    if is_contact_lookup(current):
        return True
    return bool(PERSON_CUE.search(current) or LOOKUP_CUE.search(current)) and not POLICY_CUE.search(current)


def drop_unrelated_directory_data(question: str, data: dict) -> bool:
    """조회 의도가 없는데 사원·연락처 데이터가 붙었다면 제거합니다. 제거했으면 True."""
    if not any(data.get(key) for key in DIRECTORY_KEYS) or directory_lookup_intent(question):
        return False
    for key in DIRECTORY_KEYS:
        data.pop(key, None)
    return True
