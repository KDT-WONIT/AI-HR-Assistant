"""'입사 몇 년차야?' 같은 근속 질문: 사원 정보의 입사일로 코드에서 직접 계산합니다.

규정 문서에는 개인의 근속 기간이 없으므로 RAG 검색으로 답할 수 없습니다.
입사일은 이미 사원 데이터에 있으므로, 질문이 근속을 묻는 것이면 입사일로 계산해 바로 답합니다.
"""
import re
from datetime import date

# 규정·제도를 묻는 질문(근속 N년마다 가산 등)은 개인 근속 계산 대상이 아닙니다.
POLICY_WORDS = re.compile(r'규정|부여|가산|수당|기준|인정|조건|자격|제도|산정|포상')
TENURE_PATTERN = re.compile(
    r'몇\s*년\s*차|몇\s*년\s*(?:이나\s*)?(?:됐|되었|됬|지났|째)|근속\s*(?:연수|기간|년수|몇)|'
    r'(?:입사|근무|재직|다닌|다녔)\S*\s*(?:한\s*)?(?:지\s*)?(?:몇\s*(?:년|개월|달)|얼마)')


def tenure_question(question: str) -> bool:
    from app.agent.followups import current_question
    text = current_question(question)
    return bool(TENURE_PATTERN.search(text)) and not POLICY_WORDS.search(text)


def tenure_info(hired_at: date, today: date) -> dict | None:
    """입사일 기준 근속 기간. 입사 첫해를 1년차로 셉니다(만 N년 경과 = N+1년차)."""
    months = (today.year - hired_at.year) * 12 + today.month - hired_at.month - (today.day < hired_at.day)
    if months < 0:
        return None
    return {'hired_at': hired_at.isoformat(), 'years': months // 12, 'months': months % 12, 'year_rank': months // 12 + 1,
            'as_of': today.isoformat()}
