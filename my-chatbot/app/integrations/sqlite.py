"""사원/대화 기록 DB. 문서용 ChromaDB 파일과는 별개입니다."""

import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from threading import RLock

from app.config import settings
from app.errors import StorageUnavailable

_lock = RLock()


@lru_cache(maxsize=8)
def initialize_database(path: Path):
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=10)
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
            connection.executescript(settings.sqlite_schema_path.read_text(encoding='utf-8'))
            connection.commit()
        finally:
            connection.close()


@contextmanager
def connection_scope(*, write: bool = False, path: Path | None = None):
    connection = None
    try:
        target = path or settings.sqlite_path
        initialize_database(target)
        connection = sqlite3.connect(target, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield connection
        connection.commit()
    except (sqlite3.Error, OSError) as exc:
        if connection is not None:
            connection.rollback()
        raise StorageUnavailable('SQLite 조회/저장에 실패했습니다. DB 경로와 초기화를 확인해주세요.') from exc
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()
