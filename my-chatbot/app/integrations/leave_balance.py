"""사원별 연차 잔액 계산. 원장(leave_balances)·상세(leave_balance_details)·사용 내역(leave_transactions)을 읽습니다.

잔여 = (기본 부여 + 이월 + 조정) - 사용 완료.  사용 완료는 연차를 차감하는 휴가(연차·반차·반반차)의 USED 합계입니다.
승인(APPROVED)·결재 중(PENDING) 내역은 아직 사용 전이라 잔여에서 빼지 않고, '예정 반영 시 잔여'로 따로 보여줍니다.
"""
import sqlite3
from decimal import Decimal


def _dec(value) -> Decimal:
    return Decimal(str(value or 0))


def _num(value: Decimal) -> float:
    return float(value)


def load_balance(connection, employee_id: str, year: int) -> dict | None:
    row = connection.execute(
        'SELECT granted_days,used_days,updated_at FROM leave_balances WHERE employee_id=? AND balance_year=?',
        (employee_id, year)).fetchone()
    if row is None:
        return None
    granted, used = _dec(row['granted_days']), _dec(row['used_days'])
    base, carry, adjusted = granted, Decimal(0), Decimal(0)
    try:
        detail = connection.execute(
            'SELECT base_days,carryover_days,adjusted_days FROM leave_balance_details WHERE employee_id=? AND balance_year=?',
            (employee_id, year)).fetchone()
        if detail is not None:
            base, carry, adjusted = _dec(detail['base_days']), _dec(detail['carryover_days']), _dec(detail['adjusted_days'])
    except sqlite3.OperationalError:
        pass
    scheduled, pending, upcoming, recent = Decimal(0), Decimal(0), [], []
    try:
        rows = connection.execute(
            'SELECT leave_type,start_date,end_date,days,status FROM leave_transactions '
            "WHERE employee_id=? AND deducts_annual_leave=1 AND substr(start_date,1,4)=? AND status IN ('USED','APPROVED','PENDING') "
            'ORDER BY start_date', (employee_id, str(year))).fetchall()
    except sqlite3.OperationalError:
        rows = []
    for item in rows:
        entry = dict(leave_type=item['leave_type'], start_date=item['start_date'], end_date=item['end_date'],
                     days=_num(_dec(item['days'])), status=item['status'])
        if item['status'] == 'USED':
            recent.append(entry)
        else:
            upcoming.append(entry)
            if item['status'] == 'APPROVED':
                scheduled += _dec(item['days'])
            else:
                pending += _dec(item['days'])
    remaining = granted - used
    return dict(year=year, granted_days=_num(granted), base_days=_num(base), carryover_days=_num(carry),
                adjusted_days=_num(adjusted), used_days=_num(used), remaining_days=_num(remaining),
                scheduled_days=_num(scheduled), pending_days=_num(pending),
                remaining_after_scheduled_days=_num(remaining - scheduled - pending),
                upcoming=upcoming, recent_used=recent[-3:][::-1], updated_at=row['updated_at'])


import re

BALANCE_WORDS = re.compile(r'잔여|남은|남아|남았|사용\s*(?:한|현황|내역|일수)|쓴|썼|연차\s*현황|몇\s*일|며칠|몇일|일수|부여|발생|이월')
POLICY_WORDS = re.compile(r'신청|방법|절차|규정|기준|소멸|수당|촉진|근거|조항|왜|이유')


def balance_only_question(question: str) -> bool:
    """내 연차 숫자를 묻는 질문(잔여·사용·예정)인지. 규정·절차를 함께 묻는 질문은 문서 검색 답변으로 처리합니다."""
    from app.agent.followups import current_question
    current = current_question(question)
    return bool(BALANCE_WORDS.search(current)) and not POLICY_WORDS.search(current)


def load_directory_balance(employee_id: str, year: int) -> dict | None:
    """연차 원장을 읽기 전용 사원 DB(database/employee_directory)에서 조회합니다.

    연차 데이터는 계산에만 쓰고 앱이 갱신하지 않으므로, git으로 함께 배포되는 사원 DB에 두어
    팀원이 별도 준비 없이 같은 값을 쓰게 합니다. 사원 DB를 쓰지 않거나 원장이 없으면 None을 돌려
    호출한 쪽이 앱 DB(data/app.sqlite3)에서 다시 찾습니다.
    """
    from app.config import settings
    if settings.user_data_source != 'directory':
        return None
    try:
        from app.errors import StorageUnavailable
        from app.repositories.directory import directory_connection
        with directory_connection() as connection:
            return load_balance(connection, employee_id, year)
    except (StorageUnavailable, sqlite3.Error):
        return None
