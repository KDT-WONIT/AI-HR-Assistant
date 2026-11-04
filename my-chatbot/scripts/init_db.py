""".env에 지정한 MySQL DB/테이블을 생성합니다. 기존 기록은 삭제하지 않습니다."""

import re
import sys

from app.config import PROJECT_ROOT, settings
from app.errors import StorageUnavailable
from app.integrations.mysql import get_connection


def initialize():
    if settings.storage_backend == 'sqlite':
        from app.integrations.sqlite import initialize_database
        initialize_database(settings.sqlite_path)
        return
    name = settings.mysql_database
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", name):
        raise ValueError("MYSQL_DATABASE는 영문·숫자·밑줄 1~64자여야 합니다.")
    connection = get_connection(select_database=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute(f"USE `{name}`")
            sql = settings.database_schema_path.read_text(encoding="utf-8")
            sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
            for statement in sql.split(";"):
                if statement.strip():
                    cursor.execute(statement)
            # 기존 employees 이름/입사일 컬럼을 유지한 채 사용자 정보를 확장합니다.
            for column, definition in (
                ("grade", "VARCHAR(25)"),
                ("employment_type", "VARCHAR(30)"),
                ("employment_status", "VARCHAR(20)"),
            ):
                cursor.execute("SHOW COLUMNS FROM employees LIKE %s", (column,))
                if not cursor.fetchall():
                    cursor.execute(f"ALTER TABLE employees ADD COLUMN `{column}` {definition}")
            # 이전 뼈대의 schema.sql로 생성한 DB도 데이터 삭제 없이 갱신합니다.
            cursor.execute("SHOW COLUMNS FROM conversations LIKE 'end_result'")
            if not cursor.fetchall():
                cursor.execute("ALTER TABLE conversations ADD COLUMN end_result JSON")
            cursor.execute("SHOW COLUMNS FROM messages LIKE 'sequence_id'")
            if not cursor.fetchall():
                cursor.execute("ALTER TABLE messages ADD COLUMN sequence_id BIGINT NOT NULL AUTO_INCREMENT UNIQUE")
            cursor.execute("SHOW INDEX FROM messages WHERE Key_name = 'idx_message_recent'")
            if not cursor.fetchall():
                cursor.execute("CREATE INDEX idx_message_recent ON messages (conversation_id, sequence_id)")
            # 뷰는 기존 테이블의 컬럼 추가가 끝난 뒤 생성합니다.
            view_sql = (PROJECT_ROOT / "database" / "employee_views.sql").read_text(encoding="utf-8")
            view_sql = "\n".join(line for line in view_sql.splitlines() if not line.lstrip().startswith("--"))
            for statement in view_sql.split(";"):
                if statement.strip():
                    cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()


def main():
    try:
        initialize()
    except StorageUnavailable as exc:
        sys.exit(str(exc))
    print(f"{settings.storage_backend} DB/테이블 준비 완료. 기존 기록은 유지했습니다.")


if __name__ == "__main__":
    main()
