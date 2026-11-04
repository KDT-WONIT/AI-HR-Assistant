"""가상 직원 CSV를 검증하고 .env의 MySQL에 추가합니다. 기존 행은 변경하지 않습니다."""

import argparse
import csv
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings
from app.errors import StorageUnavailable
from app.integrations.mysql import connection_scope

# 테이블/컬럼은 사용자 입력에서 가져오지 않습니다. 숫자는 최대 문자열 길이입니다.
FIELDS = {
    "departments": {"dept_id": 12, "dept_name": 80, "parent_dept_id": 12,
                    "dept_function": 200, "location": 80, "main_extension": 12, "is_active": 1},
    "duty_roles": {"role_id": 12, "role_name": 60, "role_category": 30,
                   "description": 250, "security_level": 20},
    "employees": {"employee_id": 50, "employee_name": 100, "grade": 25,
                  "hire_date": 10, "employment_type": 30, "employment_status": 20},
    "employee_assignments": {"assignment_id": 14, "employee_id": 50, "dept_id": 12,
                             "position_title": 60, "start_date": 10, "end_date": 10, "is_primary": 1},
    "employee_roles": {"employee_role_id": 14, "employee_id": 50,
                       "role_id": 12, "start_date": 10, "end_date": 10},
    "employee_contacts": {"employee_id": 50, "work_email": 130, "extension_number": 12,
                          "work_location": 100, "contact_visibility": 25,
                          "photo_path": 260, "photo_url": 500, "photo_status": 30,
                          "photo_source": 40, "photo_alt": 150},
}
REQUIRED = {
    "departments": ("dept_id", "dept_name", "is_active"),
    "duty_roles": ("role_id", "role_name"),
    "employees": ("employee_id", "employee_name", "hire_date", "employment_type", "employment_status"),
    "employee_assignments": ("assignment_id", "employee_id", "dept_id", "position_title", "start_date", "is_primary"),
    "employee_roles": ("employee_role_id", "employee_id", "role_id", "start_date"),
    "employee_contacts": ("employee_id", "contact_visibility", "photo_status"),
}


def read_rows(path: Path, fields: dict[str, int], required: tuple[str, ...]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(fields).issubset(reader.fieldnames):
            raise ValueError(f"{path.name}: 필수 CSV 열이 없습니다.")
        rows = []
        seen = set()
        key = next(iter(fields))
        for line, raw in enumerate(reader, 2):
            if None in raw or any(raw.get(field) is None for field in fields):
                raise ValueError(f"{path.name}:{line}: CSV 열 개수가 맞지 않습니다.")
            row = {field: raw[field].strip() or None for field in fields}
            for field, limit in fields.items():
                value = row[field]
                if field in required and value is None:
                    raise ValueError(f"{path.name}:{line}: {field} 값이 필요합니다.")
                if value is None:
                    continue
                if len(value) > limit:
                    raise ValueError(f"{path.name}:{line}: {field}는 {limit}자를 초과할 수 없습니다.")
                if field.endswith("_id") and not re.fullmatch(r"[A-Za-z0-9_-]+", value):
                    raise ValueError(f"{path.name}:{line}: {field} 형식이 올바르지 않습니다.")
                if field in {"hire_date", "start_date", "end_date"}:
                    row[field] = date.fromisoformat(value)
                if field in {"is_active", "is_primary"}:
                    if value not in {"0", "1"}:
                        raise ValueError(f"{path.name}:{line}: {field}는 0 또는 1이어야 합니다.")
                    row[field] = int(value)
            identity = row[key].casefold()
            if identity in seen:
                raise ValueError(f"{path.name}:{line}: 기본키가 중복되었습니다.")
            seen.add(identity)
            if row.get("end_date") and row["end_date"] < row["start_date"]:
                raise ValueError(f"{path.name}:{line}: 종료일이 시작일보다 빠릅니다.")
            rows.append(row)
    if not rows:
        raise ValueError(f"{path.name}: 데이터가 비어 있습니다.")
    return rows


def validate_url(value: str | None) -> None:
    if value and (len(value) > 500 or urlparse(value).scheme != "https" or not urlparse(value).netloc):
        raise ValueError("사진 관련 URL은 500자 이하의 HTTPS 주소여야 합니다.")


def validate_asset(dataset: Path, value: str) -> None:
    if len(value) > 260 or Path(value).is_absolute() or not (dataset / value).resolve().is_relative_to(dataset.resolve()):
        raise ValueError("사진 경로는 데이터셋 폴더 내부의 상대 경로여야 합니다.")


def load_dataset(dataset: Path) -> dict[str, list[dict]]:
    tables = {table: read_rows(dataset / "csv" / f"{table}.csv", fields, REQUIRED[table])
              for table, fields in FIELDS.items()}
    # CSV에 없는 부모를 참조하면 DB에 쓰기 전에 중단합니다.
    for table, field, parent, parent_key in (
        ("departments", "parent_dept_id", "departments", "dept_id"),
        ("employee_assignments", "employee_id", "employees", "employee_id"),
        ("employee_assignments", "dept_id", "departments", "dept_id"),
        ("employee_roles", "employee_id", "employees", "employee_id"),
        ("employee_roles", "role_id", "duty_roles", "role_id"),
        ("employee_contacts", "employee_id", "employees", "employee_id"),
    ):
        valid = {row[parent_key] for row in tables[parent]}
        if any(row[field] is not None and row[field] not in valid for row in tables[table]):
            raise ValueError(f"{table}.{field}: 존재하지 않는 {parent} 참조입니다.")
    # 부모 부서를 먼저 삽입하고 순환 참조를 검사합니다.
    pending = list(tables["departments"])
    ordered, resolved = [], set()
    while pending:
        ready = [row for row in pending if row["parent_dept_id"] is None or row["parent_dept_id"] in resolved]
        if not ready:
            raise ValueError("부서 상하 관계에 순환 참조가 있습니다.")
        ordered.extend(ready)
        resolved.update(row["dept_id"] for row in ready)
        pending = [row for row in pending if row not in ready]
    tables["departments"] = ordered
    emails = [row["work_email"].casefold() for row in tables["employee_contacts"] if row["work_email"]]
    if len(emails) != len(set(emails)):
        raise ValueError("직원 이메일이 중복되었습니다.")
    primaries = {}
    for row in tables["employee_assignments"]:
        if row["is_primary"]:
            for other in primaries.setdefault(row["employee_id"], []):
                if row["start_date"] <= (other["end_date"] or date.max) and other["start_date"] <= (row["end_date"] or date.max):
                    raise ValueError("직원의 주 소속 기간이 겹칩니다.")
            primaries[row["employee_id"]].append(row)
    manifest_fields = {"employee_id": 50, "source_page_url": 500, "license_url": 500}
    manifest = {row["employee_id"]: row for row in read_rows(
        dataset / "docs" / "employee_photo_manifest_100.csv", manifest_fields, tuple(manifest_fields))}
    employee_ids = {row["employee_id"] for row in tables["employees"]}
    contact_ids = {row["employee_id"] for row in tables["employee_contacts"]}
    if set(manifest) != employee_ids or contact_ids != employee_ids:
        raise ValueError("직원·연락처·사진 출처의 사번 목록이 일치하지 않습니다.")
    for row in tables["employee_contacts"]:
        source = manifest[row["employee_id"]]
        row.update(source_page_url=source["source_page_url"], license_url=source["license_url"],
                   fallback_photo_path=f"assets/profiles/{row['employee_id']}.svg")
        for field in ("photo_url", "source_page_url", "license_url"):
            validate_url(row[field])
        for field in ("photo_path", "fallback_photo_path"):
            if row[field]:
                validate_asset(dataset, row[field])
        if not (dataset / row["fallback_photo_path"]).is_file():
            raise ValueError("기본 프로필 아이콘 파일이 없습니다.")
        row["photo_file_status"] = "PRESENT" if row["photo_path"] and (dataset / row["photo_path"]).is_file() else "NOT_DOWNLOADED"
    return tables


def insert_dataset(tables: dict[str, list[dict]]) -> dict[str, int]:
    if settings.storage_backend == 'sqlite':
        return insert_sqlite_dataset(tables)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    counts = {}
    # 전체 적재를 한 트랜잭션으로 처리합니다. 오류 시 추가한 모든 행을 롤백합니다.
    with connection_scope() as connection, connection.cursor() as cursor:
        for table, source in tables.items():
            rows = source
            if table == "employees":
                rows = [{"employee_id": row["employee_id"], "name": row["employee_name"],
                         "hired_at": row["hire_date"], "grade": row["grade"],
                         "employment_type": row["employment_type"],
                         "employment_status": row["employment_status"], "created_at": now} for row in source]
            columns = list(rows[0])
            key = columns[0]
            names = ", ".join(f"`{column}`" for column in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            query = (f"INSERT INTO `{table}` ({names}) SELECT {placeholders} "
                     f"WHERE NOT EXISTS (SELECT 1 FROM `{table}` WHERE `{key}` = %s)")
            counts[table] = 0
            for row in rows:
                cursor.execute(query, tuple(row[column] for column in columns) + (row[key],))
                counts[table] += cursor.rowcount
    return counts


def insert_sqlite_dataset(tables: dict[str, list[dict]]) -> dict[str, int]:
    from app.integrations.sqlite import connection_scope as sqlite_connection
    counts = {}
    now = datetime.now(timezone.utc).isoformat()
    with sqlite_connection(write=True) as connection:
        for table, source in tables.items():
            if table not in FIELDS:
                raise ValueError('등록되지 않은 직원 테이블입니다.')
            counts[table] = 0
            for original in source:
                row = dict(original)
                if table == 'employees':
                    row['name'] = row.pop('employee_name')
                    row['hired_at'] = row.pop('hire_date')
                    row['created_at'] = now
                columns = list(row)
                if not all(re.fullmatch(r'[a-z_]+', column) for column in columns):
                    raise ValueError('잘못된 컬럼입니다.')
                values = [value.isoformat() if isinstance(value, (date, datetime)) else value for value in row.values()]
                key = columns[0]
                if connection.execute(f'SELECT 1 FROM "{table}" WHERE "{key}"=?', (values[0],)).fetchone():
                    continue
                names = ','.join(f'"{name}"' for name in columns)
                connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({",".join("?" for _ in columns)})', values)
                counts[table] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=settings.employee_dataset_dir)
    parser.add_argument("--check-only", action="store_true", help="DB 연결 없이 데이터만 검증")
    args = parser.parse_args()
    try:
        tables = load_dataset(args.dataset_dir.resolve())
        print("직원 데이터 검증 완료: " + ", ".join(f"{table}={len(rows)}" for table, rows in tables.items()))
        if args.check_only:
            return
        counts = insert_dataset(tables)
        for table, count in counts.items():
            print(f"{table}: {count}행 추가 / 기존 행 유지")
    except (ValueError, OSError, StorageUnavailable) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
