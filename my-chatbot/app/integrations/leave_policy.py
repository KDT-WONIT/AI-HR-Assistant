"""입사일로 연차유급휴가 부여일수를 계산합니다(취업규칙 제20조, 시행세칙 제9조).

연차 사용 이력 DB가 없는 환경에서 사원 정보(입사일·직급)만으로 `부여일수`를 규정대로 계산합니다.
실제로 이미 사용한 일수는 알 수 없으므로 잔여일수를 단정하지 않습니다.

- 계산기간: 입사일(기념일)부터 다음 기념일 전날까지
- 입사 1년 미만: 1개월 개근 시 1일씩 발생(최대 11일)
- 입사 1년 이상, 계산기간 80% 이상 출근: 15일. 3년 이상 계속 근무하면 최초 1년을 넘는 계속근로연수 2년마다 1일 가산, 최대 25일
- 의무사용(사용촉진) 일수: 3직급 이하 24일, 2직급 이상 25일
"""

import re
from datetime import date, timedelta

BASE_DAYS, MAX_DAYS, FIRST_YEAR_MAX = 15, 25, 11


def anniversary(hired_at: date, years: int) -> date:
    try:
        return hired_at.replace(year=hired_at.year + years)
    except ValueError:  # 2월 29일 입사자의 평년 기념일은 2월 28일로 봅니다.
        return hired_at.replace(year=hired_at.year + years, day=28)


def completed_years(hired_at: date, as_of: date) -> int:
    years = as_of.year - hired_at.year
    while years > 0 and anniversary(hired_at, years) > as_of:
        years -= 1
    return years


def completed_months(hired_at: date, as_of: date) -> int:
    months = (as_of.year - hired_at.year) * 12 + as_of.month - hired_at.month
    return max(0, months - (as_of.day < hired_at.day))


def annual_days(years: int) -> int:
    """계속 근무 `years`년을 채운 직원에게 그 기념일부터 1년간 부여되는 연차일수."""
    return min(MAX_DAYS, BASE_DAYS + max(0, years - 1) // 2)


def mandatory_use_days(grade: str | None) -> int | None:
    match = re.match(r'\s*(\d+)\s*직급', grade or '')
    if not match:
        return None
    return 25 if int(match.group(1)) <= 2 else 24


def leave_entitlement(hired_at: date, as_of: date, grade: str | None = None) -> dict | None:
    if hired_at is None or as_of < hired_at:
        return None
    years = completed_years(hired_at, as_of)
    if years == 0:
        start, end = hired_at, anniversary(hired_at, 1) - timedelta(days=1)
        months = min(FIRST_YEAR_MAX, completed_months(hired_at, as_of))
        result = {'kind': 'first_year', 'granted_days': months, 'max_days_in_period': FIRST_YEAR_MAX,
                  'basis': f'입사 1년 미만은 1개월 개근마다 1일 발생합니다(최대 {FIRST_YEAR_MAX}일). 오늘까지 {months}개월 경과.'}
    else:
        start, end = anniversary(hired_at, years), anniversary(hired_at, years + 1) - timedelta(days=1)
        days = annual_days(years)
        extra = days - BASE_DAYS
        result = {'kind': 'annual', 'granted_days': days, 'max_days_in_period': days,
                  'basis': f'계속근로 {years}년: 기본 {BASE_DAYS}일' + (f' + 가산 {extra}일(최초 1년 초과 근속 2년마다 1일, 최대 {MAX_DAYS}일)' if extra else '')
                           + '. 계산기간 80% 이상 출근을 전제로 합니다.'}
        if days < MAX_DAYS:
            result['next_anniversary_days'] = annual_days(years + 1)
    result.update({'hired_at': hired_at.isoformat(), 'as_of': as_of.isoformat(), 'completed_years': years,
                   'period_start': start.isoformat(), 'period_end': end.isoformat(),
                   'mandatory_use_days': mandatory_use_days(grade),
                   'source': '취업규칙 제20조·취업규칙 시행세칙 제9조',
                   'note': '사용 이력 데이터가 없어 이미 사용한 연차는 반영하지 않았습니다. 토요일·휴일은 연차일수에 산입하지 않습니다.'})
    return result
