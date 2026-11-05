import re


def canonical_employee_id(value: str) -> str:
    """이전 브라우저 세션의 사번도 현재 DB의 동일 사원으로 연결합니다."""
    return re.sub(r'^KDN(?=\d+$)', 'WON', value.strip(), flags=re.I)
