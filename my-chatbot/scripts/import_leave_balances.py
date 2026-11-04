"""연차 부여/사용 기록 CSV를 SQLite에 등록합니다. 사내 규정으로 부여 일수를 추측하지 않습니다."""

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field
from app.config import resolve_path, settings
from app.errors import StorageUnavailable
from app.integrations.sqlite import connection_scope


class LeaveRow(BaseModel):
    employee_id: str = Field(min_length=1, max_length=50)
    year: int = Field(ge=1900, le=2200)
    granted_days: float = Field(ge=0, le=366, allow_inf_nan=False)
    used_days: float = Field(ge=0, le=366, allow_inf_nan=False)


def import_balances(path: Path) -> int:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = [LeaveRow.model_validate(row) for row in csv.DictReader(stream)]
    keys = [(row.employee_id, row.year) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('사번과 연도가 중복되었습니다.')
    profiles = {}
    if settings.user_data_source == 'directory':
        from app.repositories.directory import EmployeeDirectoryRepository
        directory = EmployeeDirectoryRepository()
        for employee_id,_ in keys:
            profile = directory.get(employee_id)
            if profile is None:
                raise ValueError(f'사원 디렉터리에 등록되지 않은 사번입니다: {employee_id}')
            profiles[employee_id] = profile
    with connection_scope(write=True) as connection:
        # 원장의 기존 사번 외래키를 유지하기 위한 참조 행입니다. 프로필의 조회 원본은 독립 사원 DB입니다.
        for profile in profiles.values():
            connection.execute(
                'INSERT INTO employees(employee_id,name,department,job_title,hired_at,grade,employment_type,employment_status,created_at) '
                'VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(employee_id) DO NOTHING',
                (profile.employee_id,profile.name,profile.department,profile.job_title,
                 profile.hired_at.isoformat() if profile.hired_at else None,profile.grade,profile.employment_type,
                 profile.employment_status,datetime.now(timezone.utc).isoformat()),
            )
        for row in rows:
            if row.used_days > row.granted_days:
                raise ValueError('사용 일수가 부여 일수보다 큽니다.')
            connection.execute(
                'INSERT INTO leave_balances VALUES(?,?,?,?,?) ON CONFLICT(employee_id,balance_year) '
                'DO UPDATE SET granted_days=excluded.granted_days,used_days=excluded.used_days,updated_at=excluded.updated_at',
                (row.employee_id, row.year, row.granted_days, row.used_days, datetime.now(timezone.utc).isoformat()),
            )
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True)
    args = parser.parse_args()
    try:
        count = import_balances(resolve_path(args.file))
    except (ValueError, OSError, StorageUnavailable) as exc:
        parser.exit(1, str(exc) + '\n')
    print(f'연차 기록 {count}개 등록/갱신 완료')


if __name__ == '__main__':
    main()
