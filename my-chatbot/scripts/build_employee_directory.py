"""기존 SQL에서 사원·조직·연락처·사진 DB만 추출한 독립 배포본을 만듭니다."""

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from app.config import PROJECT_ROOT, settings
from scripts.seed_employees import FIELDS, load_dataset

TABLES = tuple(FIELDS)
SOURCES = ("01_create_schema.sql", "02_seed_data.sql", "03_example_queries.sql",
           "04_load_csv.py", "04_OLD_randomuser_do_not_run.sql", "04_update_100_pexels_photos.sql")


def selected_inserts(text: str) -> dict[str, list[str]]:
    """허용한 테이블의 INSERT 한 문장만 추출합니다. 다른 SQL은 실행하지 않습니다."""
    result, lines, table = {}, [], None
    for line in text.splitlines(keepends=True):
        if table is None:
            match = re.match(r"INSERT INTO `([a-z_]+)` \(", line)
            if not match or match[1] not in TABLES:
                continue
            table, lines = match[1], []
        lines.append(line)
        if sqlite3.complete_statement("".join(lines)):
            result.setdefault(table, []).append("".join(lines).strip())
            table = None
    if table or set(result) != set(TABLES):
        raise ValueError("원본 SQL에 필요한 사원 테이블 데이터가 없습니다.")
    return result


def normalized(value):
    return None if value is None else str(value)


def load_source(source: Path) -> dict[str, list[dict]]:
    # 기존 CSV 검증을 재사용하고 첨부 SQL의 실제 값과도 전 필드를 대조합니다.
    tables = load_dataset(source)
    inserts = selected_inserts((source / "sql" / "02_seed_data.sql").read_text(encoding="utf-8-sig"))
    with closing(sqlite3.connect(":memory:")) as scratch:
        scratch.row_factory = sqlite3.Row
        for table in TABLES:
            fields = FIELDS[table]
            key = next(iter(fields))
            declarations = ", ".join(f'"{field}" TEXT' + (" PRIMARY KEY" if field == key else "") for field in fields)
            scratch.execute(f'CREATE TABLE "{table}" ({declarations})')
            # execute는 복수 문장을 허용하지 않습니다. 선별한 INSERT만 메모리에서 읽습니다.
            for statement in inserts[table]:
                scratch.execute(statement)
        updates = (source / "sql" / "04_update_100_pexels_photos.sql").read_text(encoding="utf-8-sig")
        updated = set()
        for line in updates.splitlines():
            if not line.startswith("UPDATE `employee_contacts` SET "):
                continue
            match = re.fullmatch(
                r"UPDATE `employee_contacts` SET (.+) WHERE `employee_id`='([A-Za-z0-9_-]+)';", line)
            if not match:
                raise ValueError("사진 업데이트 SQL 형식을 확인해주세요.")
            # 사진의 문자열 리터럴 대입만 허용합니다. 원본 전체를 실행하지 않습니다.
            assignments = re.findall(r"`([a-z_]+)`='((?:[^']|'')*)'", match[1])
            reconstructed = ", ".join(f"`{key}`='{value}'" for key, value in assignments)
            allowed = {"photo_path", "photo_url", "photo_status", "photo_source", "photo_alt"}
            if reconstructed != match[1] or {key for key, _ in assignments} != allowed or match[2] in updated:
                raise ValueError("사진 업데이트에는 허용한 다섯 필드만 필요합니다.")
            values = [value.replace("''", "'") for _, value in assignments]
            query = "UPDATE employee_contacts SET " + ", ".join(f'"{key}"=?' for key, _ in assignments)
            changed = scratch.execute(query + " WHERE employee_id=?", [*values, match[2]]).rowcount
            if changed != 1:
                raise ValueError("사진 업데이트의 사번이 사원 데이터와 일치하지 않습니다.")
            updated.add(match[2])
        if updated != {row["employee_id"] for row in tables["employees"]}:
            raise ValueError("사진 업데이트가 전체 사원과 일치하지 않습니다.")
        for table, rows in tables.items():
            key = next(iter(FIELDS[table]))
            sql_rows = {row[key]: dict(row) for row in scratch.execute(f'SELECT * FROM "{table}"')}
            if set(sql_rows) != {row[key] for row in rows}:
                raise ValueError(f"SQL과 CSV의 기본키 목록이 다릅니다: {table}")
            for row in rows:
                original = sql_rows[row[key]]
                for field in FIELDS[table]:
                    if table == "employee_contacts" and field == "photo_alt":
                        row[field] = original[field]  # 최신 Pexels 패치의 설명을 반영합니다.
                    elif normalized(row[field]) != normalized(original[field]):
                        raise ValueError(f"SQL과 CSV 값이 다릅니다: {table}.{field}")
    return tables


def table_ddl(text: str) -> str:
    found = {match[1]: match[0] for match in re.finditer(
        r"CREATE TABLE IF NOT EXISTS ([a-z_]+) \([\s\S]*?\n\);", text)}
    if not set(TABLES).issubset(found):
        raise ValueError("프로젝트 스키마에 필요한 테이블이 없습니다.")
    return "\n\n".join(found[table] for table in TABLES)


def converted_rows(tables: dict[str, list[dict]], created_at: str) -> dict[str, list[dict]]:
    result = {}
    for table, rows in tables.items():
        result[table] = []
        for original in rows:
            row = {field: value.isoformat() if isinstance(value, (date, datetime)) else value
                   for field, value in original.items()}
            if table == "employees":
                row["name"] = row.pop("employee_name")
                row["hired_at"] = row.pop("hire_date")
                row["created_at"] = created_at
            result[table].append(row)
    return result


def literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    # MySQL의 백슬래시 처리 설정에 의존하지 않는 UTF-8 문자열입니다.
    return "CONVERT(X'" + str(value).encode("utf-8").hex() + "' USING utf8mb4) COLLATE utf8mb4_unicode_ci"


def mysql_seed(tables: dict[str, list[dict]]) -> str:
    statements = ["-- 가상 사원 자료. 기존 기본키의 행은 변경하지 않습니다.",
                  "USE `employee_directory`;", "SET NAMES utf8mb4;", "START TRANSACTION;"]
    for table, rows in tables.items():
        statements.append(f"\n-- {table}: {len(rows)} rows")
        for row in rows:
            key = next(iter(row))
            columns = ", ".join(f"`{field}`" for field in row)
            values = ", ".join(literal(value) for value in row.values())
            statements.append(f"INSERT INTO `{table}` ({columns}) SELECT {values} "
                              f"WHERE NOT EXISTS (SELECT 1 FROM `{table}` WHERE `{key}`={literal(row[key])});")
    statements.append("COMMIT;")
    return "\n".join(statements) + "\n"


def build(source: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"기존 결과를 보호하기 위해 중단합니다. 새 출력 폴더를 지정해주세요: {output}")
    tables = load_source(source)
    created_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    tables = converted_rows(tables, created_at)
    mysql_schema = table_ddl((PROJECT_ROOT / "database/schema.sql").read_text(encoding="utf-8"))
    mysql_views = (PROJECT_ROOT / "database/employee_views.sql").read_text(encoding="utf-8")
    sqlite_source = (PROJECT_ROOT / "database/sqlite_schema.sql").read_text(encoding="utf-8")
    sqlite_views = re.search(r"CREATE VIEW IF NOT EXISTS v_employee_profiles[\s\S]*?;", sqlite_source)[0]
    sqlite_schema = table_ddl(sqlite_source) + "\n\n" + sqlite_views
    manifest = {
        "created_at_utc": created_at, "database": "employee_directory", "fictional_data": True,
        "counts": {table: len(rows) for table, rows in tables.items()},
        "sources": {name: hashlib.sha256((source / "sql" / name).read_bytes()).hexdigest() for name in SOURCES},
        "selection": "사원, 부서, 소속 이력, 업무 역할, 사원별 역할, 연락처/사진",
        "excluded": ["규정/문서", "급여/복지", "근태/휴가", "대화/상담", "구버전 RandomUser 사진"],
        "photo_originals": "NOT_DOWNLOADED", "photo_review": "REVIEW_PENDING",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="employee-directory-", dir=output.parent) as work:
        stage = Path(work) / "package"
        stage.mkdir()
        header = ("-- 독립 사원/조직 DB. 앱의 기본 DB와 별도로 생성합니다.\n"
                  "CREATE DATABASE IF NOT EXISTS `employee_directory` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
                  "USE `employee_directory`;\nSET NAMES utf8mb4;\n\n")
        (stage / "01_create_schema.sql").write_text(header + mysql_schema + "\n\n" + mysql_views, encoding="utf-8")
        (stage / "02_seed_data.sql").write_text(mysql_seed(tables), encoding="utf-8")
        (stage / "sqlite_schema.sql").write_text(sqlite_schema + "\n", encoding="utf-8")
        queries = (PROJECT_ROOT / "database/employee_directory_queries.sql").read_text(encoding="utf-8")
        (stage / "03_example_queries.sql").write_text("USE `employee_directory`;\n\n" + queries, encoding="utf-8")
        (stage / "queries_sqlite.sql").write_text(queries, encoding="utf-8")
        (stage / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        shutil.copyfile(PROJECT_ROOT / "docs/employee-directory-package.md", stage / "README.md")
        (stage / "assets/profiles").mkdir(parents=True)
        for row in tables["employee_contacts"]:
            shutil.copyfile(source / row["fallback_photo_path"], stage / row["fallback_photo_path"])
        with closing(sqlite3.connect(stage / "employee_directory.sqlite3")) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(sqlite_schema)
            with connection:
                for table, rows in tables.items():
                    columns = ", ".join(f'"{field}"' for field in rows[0])
                    placeholders = ", ".join("?" for _ in rows[0])
                    connection.executemany(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})',
                                           [tuple(row.values()) for row in rows])
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("생성한 DB의 무결성 검사에 실패했습니다.")
            for statement in queries.split(";"):
                if statement.strip():
                    connection.execute(statement).fetchall()
        stage.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=settings.employee_dataset_dir)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "database/employee_directory")
    args = parser.parse_args()
    manifest = build(args.source_dir.resolve(), args.output_dir.resolve())
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    print(f"사원 DB 묶음 생성 완료: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
