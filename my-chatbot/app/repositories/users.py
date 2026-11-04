"""사용자 기본 정보는 대화 이력과 분리해서 관리합니다."""

import json
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from app.config import settings
from app.errors import StorageUnavailable
from app.integrations.mysql import connection_scope
from app.schemas import UserProfile


class UserRepository(Protocol):
    def get(self, employee_id: str) -> UserProfile | None: ...


def load_profiles(path: Path) -> list[UserProfile]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        profiles = TypeAdapter(list[UserProfile]).validate_python(data)
        if len({item.employee_id for item in profiles}) != len(profiles):
            raise ValueError("duplicate user ID")
        return profiles
    except (OSError, ValueError, ValidationError) as exc:
        raise StorageUnavailable("사용자 데이터 파일을 읽을 수 없습니다. JSON 형식·필드·중복 ID를 확인해주세요.") from exc


class FileUserRepository:
    def __init__(self, path: Path | None = None):
        self.path = settings.user_data_path if path is None else path

    def get(self, employee_id: str) -> UserProfile | None:
        if not self.path.exists():
            return None
        # 요청마다 읽으므로 파일을 수정하면 다음 질문부터 새 정보가 반영됩니다.
        return next((profile for profile in load_profiles(self.path) if profile.employee_id == employee_id), None)


class MySQLUserRepository:
    def get(self, employee_id: str) -> UserProfile | None:
        with connection_scope() as connection, connection.cursor(dictionary=True) as cursor:
            # 전체 사용자 테이블 대신 지정한 ID의 기본 필드만 조회합니다.
            cursor.execute(
                "SELECT employee_id, name, department, job_title, hired_at FROM v_employee_profiles WHERE employee_id = %s",
                (employee_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            try:
                return UserProfile.model_validate(row)
            except ValidationError as exc:
                raise StorageUnavailable("사용자 DB의 기본 정보 형식을 확인해주세요.") from exc


class SQLiteUserRepository:
    def get(self, employee_id: str) -> UserProfile | None:
        from app.integrations.sqlite import connection_scope as sqlite_connection
        with sqlite_connection() as connection:
            row = connection.execute(
                'SELECT employee_id,name,department,job_title,hired_at,grade,employment_type,employment_status '
                'FROM v_employee_profiles WHERE employee_id=?', (employee_id,),
            ).fetchone()
            return UserProfile.model_validate(dict(row)) if row is not None else None


def create_user_repository(conversation_storage: str) -> UserRepository:
    source = settings.user_data_source
    if source == "auto":
        source = conversation_storage if conversation_storage in {"mysql", "sqlite"} else "file"
    if source == "sqlite":
        return SQLiteUserRepository()
    if source == 'directory':
        from app.repositories.directory import EmployeeDirectoryRepository
        return EmployeeDirectoryRepository()
    return MySQLUserRepository() if source == "mysql" else FileUserRepository()
