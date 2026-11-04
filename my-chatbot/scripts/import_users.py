"""가상 사용자 JSON을 MySQL employees에 등록/갱신합니다. 대화 기록은 변경하지 않습니다."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import resolve_path, settings
from app.errors import StorageUnavailable
from app.integrations.mysql import connection_scope
from app.repositories.users import load_profiles


def import_profiles(path: Path) -> int:
    profiles = load_profiles(path)
    if settings.storage_backend == 'sqlite':
        from app.integrations.sqlite import connection_scope as sqlite_connection
        with sqlite_connection(write=True) as connection:
            for profile in profiles:
                connection.execute(
                    'INSERT INTO employees(employee_id,name,department,job_title,hired_at,created_at) VALUES(?,?,?,?,?,?) '
                    'ON CONFLICT(employee_id) DO UPDATE SET name=excluded.name,department=excluded.department,'
                    'job_title=excluded.job_title,hired_at=excluded.hired_at',
                    (profile.employee_id, profile.name, profile.department, profile.job_title,
                     profile.hired_at.isoformat() if profile.hired_at else None, datetime.now(timezone.utc).isoformat()),
                )
        return len(profiles)
    with connection_scope() as connection, connection.cursor() as cursor:
        for profile in profiles:
            values = (profile.name, profile.department, profile.job_title, profile.hired_at)
            cursor.execute(
                "INSERT INTO employees (employee_id, name, department, job_title, hired_at, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE "
                "name = %s, department = %s, job_title = %s, hired_at = %s",
                (profile.employee_id, *values, datetime.now(timezone.utc).replace(tzinfo=None), *values),
            )
    return len(profiles)


def main():
    parser = argparse.ArgumentParser(description='사용자 JSON → MySQL employees 등록/갱신')
    parser.add_argument('--file', help='생략하면 .env USER_DATA_PATH 사용')
    args = parser.parse_args()
    try:
        count = import_profiles(resolve_path(args.file) if args.file else settings.user_data_path)
    except StorageUnavailable as exc:
        sys.exit(str(exc))
    print(f'사용자 정보 {count}개 등록/갱신 완료. 대화 기록은 유지했습니다.')


if __name__ == '__main__':
    main()
