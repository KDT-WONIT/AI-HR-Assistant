from contextlib import contextmanager

from app.config import settings
from app.errors import StorageUnavailable


def get_connection(*, select_database: bool = True):
    if not settings.mysql_user:
        raise StorageUnavailable(".env에 MYSQL_USER와 접속정보를 설정해주세요.")
    try:
        import mysql.connector
    except ImportError as exc:
        raise StorageUnavailable("requirements.txt의 MySQL 패키지를 설치해주세요.") from exc
    options = dict(
        host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password,
        charset="utf8mb4", autocommit=False, connection_timeout=3,
        time_zone="+00:00",
    )
    if select_database:
        options["database"] = settings.mysql_database
    try:
        return mysql.connector.connect(**options)
    except mysql.connector.Error as exc:
        raise StorageUnavailable("MySQL 연결에 실패했습니다. 접속정보와 DB 초기화를 확인해주세요.") from exc


@contextmanager
def connection_scope():
    """각 작업에 독립된 연결/트랜잭션을 사용합니다."""
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception as exc:
        try:
            connection.rollback()
        except Exception:
            pass
        from mysql.connector import Error
        if isinstance(exc, Error):
            raise StorageUnavailable("MySQL 읽기/저장에 실패했습니다. DB 초기화와 서버 상태를 확인해주세요.") from exc
        raise
    finally:
        connection.close()
