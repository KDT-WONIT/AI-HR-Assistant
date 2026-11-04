"""모든 실행 설정의 단일 진입점. 다른 모듈에서는 settings만 가져옵니다."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False, encoding="utf-8-sig")


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def env_path(env: Mapping[str, str], key: str, fallback: Path) -> Path:
    return resolve_path(env.get(key, "").strip() or fallback)


def env_int(env: Mapping[str, str], key: str, fallback: int) -> int:
    try:
        return int(env.get(key, str(fallback)))
    except ValueError:
        raise ValueError(f"{key}는 정수여야 합니다.") from None


@dataclass(frozen=True)
class Settings:
    mode: str = "demo"
    storage_backend: str = "sqlite"
    history_message_limit: int = 10
    answer_provider: str = "ollama"
    tool_router: str = "ollama"
    enabled_tools: tuple[str, ...] = ()
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_answer_model: str = 'gemma3:4b'
    ollama_timeout: float = 60
    mcp_timeout: float = 180
    contact_recommendation_limit: int = 2
    contact_routing_path: Path = PROJECT_ROOT / 'config' / 'contact_topics.json'
    travel_grade_mapping_path: Path = PROJECT_ROOT / 'config' / 'travel_grades.json'
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "ai_hr_assistant"
    mysql_user: str = ""
    mysql_password: str = field(default="", repr=False)
    embedding_model: str = "BAAI/bge-m3"
    embedding_revision: str = "5617a9f61b028005a4858fdac845db406aefb181"
    embedding_device: str = "cpu"
    rag_top_k: int = 5
    rag_max_distance: float = 0.60
    n8n_webhook_url: str = field(default="", repr=False)
    n8n_timeout: float = 10
    n8n_message_limit: int = 10
    n8n_message_max_chars: int = 1000
    n8n_event_session_start: str = 'session_start'
    n8n_event_question: str = 'question'
    n8n_event_answer: str = 'answer'
    n8n_event_session_end: str = 'session_end'
    vector_backend: str = "chroma"
    chroma_collection: str = "kdn_regulations_bge_m3_v1"
    user_data_source: str = "auto"
    frontend_dir: Path = PROJECT_ROOT / "frontend"
    prompts_dir: Path = PROJECT_ROOT / "prompts"
    logs_dir: Path = PROJECT_ROOT / "logs"
    database_schema_path: Path = PROJECT_ROOT / "database" / "schema.sql"
    data_dir: Path = PROJECT_ROOT / "data"
    policy_dir: Path = PROJECT_ROOT / "data" / "raw" / "policies"
    csv_dir: Path = PROJECT_ROOT / "data" / "raw" / "csv"
    employee_dataset_dir: Path = PROJECT_ROOT.parent / "data" / "KDN_Enterprise_AI_Dataset" / "KDN_Enterprise_AI_Dataset_Pexels"
    employee_directory_dir: Path = PROJECT_ROOT / 'database' / 'employee_directory'
    employee_directory_db: Path = PROJECT_ROOT / 'database' / 'employee_directory' / 'employee_directory.sqlite3'
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    chunks_dir: Path = PROJECT_ROOT / "data" / "processed" / "chunks"
    vector_dir: Path = PROJECT_ROOT / "data" / "vector_store"
    chroma_dir: Path = PROJECT_ROOT.parent / 'kdn_regulations_rag' / 'rag_data' / 'chroma_db'
    sqlite_path: Path = PROJECT_ROOT / "data" / "app.sqlite3"
    sqlite_schema_path: Path = PROJECT_ROOT / 'database' / 'sqlite_schema.sql'
    embedding_cache_dir: Path = PROJECT_ROOT / "data" / "models"
    user_data_path: Path = PROJECT_ROOT / "data" / "raw" / "users.json"

    def __post_init__(self):
        for name, value, allowed in (
            ("APP_MODE", self.mode, {"demo", "live"}),
            ("STORAGE_BACKEND", self.storage_backend, {"memory", "mysql", "sqlite"}),
            ("ANSWER_PROVIDER", self.answer_provider, {"demo", "ollama"}),
            ("VECTOR_BACKEND", self.vector_backend, {"chroma"}),
            ("USER_DATA_SOURCE", self.user_data_source, {"auto", "file", "mysql", "sqlite", "directory"}),
            ("TOOL_ROUTER", self.tool_router, {"ollama", "manual"}),
        ):
            if value not in allowed:
                raise ValueError(f"{name}는 {', '.join(sorted(allowed))} 중 하나여야 합니다.")
        if not 5 <= self.history_message_limit <= 10:
            raise ValueError("HISTORY_MESSAGE_LIMIT은 5~10이어야 합니다. 질문/답변 각각 1개로 계산합니다.")
        if self.ollama_timeout <= 0:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS는 양수여야 합니다.")
        if self.mcp_timeout <= 0:
            raise ValueError('MCP_TIMEOUT_SECONDS는 양수여야 합니다.')
        if not 1 <= self.contact_recommendation_limit <= 5:
            raise ValueError('CONTACT_RECOMMENDATION_LIMIT은 1~5여야 합니다.')
        if self.n8n_timeout <= 0 or not 1 <= self.n8n_message_limit <= 50 or not 100 <= self.n8n_message_max_chars <= 4000:
            raise ValueError('n8n 제한값을 확인해주세요. 시간>0, 메시지 1~50개, 메시지 길이 100~4000자입니다.')
        if self.n8n_webhook_url:
            from urllib.parse import urlparse
            parsed = urlparse(self.n8n_webhook_url)
            if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
                raise ValueError('N8N_WEBHOOK_URL은 http 또는 https 주소여야 합니다.')
        event_names = [self.n8n_event_session_start,self.n8n_event_question,self.n8n_event_answer,self.n8n_event_session_end]
        if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}',name) for name in event_names) or len(set(event_names)) != 4:
            raise ValueError('n8n 이벤트 이름은 서로 달라야 하며 영문으로 시작하는 1~64자 영문·숫자·밑줄·점·하이픈이어야 합니다.')
        if not 1 <= self.mysql_port <= 65535:
            raise ValueError("MYSQL_PORT는 1~65535여야 합니다.")
        if not self.chroma_collection.strip():
            raise ValueError("CHROMA_COLLECTION은 비워둘 수 없습니다.")
        if not 1 <= self.rag_top_k <= 20 or not 0 <= self.rag_max_distance <= 2:
            raise ValueError("RAG_TOP_K는 1~20, RAG_MAX_DISTANCE는 0~2여야 합니다.")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        data = env_path(env, "DATA_DIR", PROJECT_ROOT / "data")
        processed = env_path(env, "PROCESSED_DIR", data / "processed")
        vector = env_path(env, "VECTOR_DIR", data / "vector_store")
        directory = env_path(env, 'EMPLOYEE_DIRECTORY_DIR', PROJECT_ROOT / 'database' / 'employee_directory')
        try:
            timeout = float(env.get("OLLAMA_TIMEOUT_SECONDS", "60"))
        except ValueError:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS는 숫자여야 합니다.") from None
        return cls(
            mode=env.get("APP_MODE", "demo"), storage_backend=env.get("STORAGE_BACKEND", "sqlite"),
            history_message_limit=env_int(env, "HISTORY_MESSAGE_LIMIT", 10),
            answer_provider=env.get("ANSWER_PROVIDER", "ollama"),
            tool_router=env.get("TOOL_ROUTER", "ollama"),
            enabled_tools=tuple(item.strip() for item in env.get("ENABLED_TOOLS", "").split(",") if item.strip()),
            ollama_base_url=env.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_model=env.get("OLLAMA_MODEL", "qwen2.5:3b"), ollama_timeout=timeout,
            ollama_answer_model=env.get('OLLAMA_ANSWER_MODEL', 'gemma3:4b'),
            mcp_timeout=float(env.get('MCP_TIMEOUT_SECONDS', '180')),
            contact_recommendation_limit=env_int(env, 'CONTACT_RECOMMENDATION_LIMIT', 2),
            contact_routing_path=env_path(env,'CONTACT_ROUTING_PATH',PROJECT_ROOT/'config'/'contact_topics.json'),
            travel_grade_mapping_path=env_path(env,'TRAVEL_GRADE_MAPPING_PATH',PROJECT_ROOT/'config'/'travel_grades.json'),
            mysql_host=env.get("MYSQL_HOST", "127.0.0.1"), mysql_port=env_int(env, "MYSQL_PORT", 3306),
            mysql_database=env.get("MYSQL_DATABASE", "ai_hr_assistant"),
            mysql_user=env.get("MYSQL_USER", ""), mysql_password=env.get("MYSQL_PASSWORD", ""),
            embedding_model=env.get("EMBEDDING_MODEL", "BAAI/bge-m3"), n8n_webhook_url=env.get("N8N_WEBHOOK_URL", ""),
            n8n_timeout=float(env.get('N8N_TIMEOUT_SECONDS', '10')),
            n8n_message_limit=env_int(env, 'N8N_MESSAGE_LIMIT', 10),
            n8n_message_max_chars=env_int(env, 'N8N_MESSAGE_MAX_CHARS', 1000),
            n8n_event_session_start=env.get('N8N_EVENT_SESSION_START','session_start'),
            n8n_event_question=env.get('N8N_EVENT_QUESTION','question'),
            n8n_event_answer=env.get('N8N_EVENT_ANSWER','answer'),
            n8n_event_session_end=env.get('N8N_EVENT_SESSION_END','session_end'),
            embedding_revision=env.get("EMBEDDING_REVISION", "5617a9f61b028005a4858fdac845db406aefb181"),
            embedding_device=env.get("EMBEDDING_DEVICE", "cpu"),
            rag_top_k=env_int(env, "RAG_TOP_K", 5), rag_max_distance=float(env.get("RAG_MAX_DISTANCE", "0.60")),
            vector_backend=env.get("VECTOR_BACKEND", "chroma"),
            chroma_collection=env.get("CHROMA_COLLECTION", "kdn_regulations_bge_m3_v1"),
            user_data_source=env.get("USER_DATA_SOURCE", "auto"),
            frontend_dir=env_path(env, "FRONTEND_DIR", PROJECT_ROOT / "frontend"),
            prompts_dir=env_path(env, "PROMPTS_DIR", PROJECT_ROOT / "prompts"),
            logs_dir=env_path(env, "LOGS_DIR", PROJECT_ROOT / "logs"),
            database_schema_path=env_path(env, "DATABASE_SCHEMA_PATH", PROJECT_ROOT / "database" / "schema.sql"),
            data_dir=data, policy_dir=env_path(env, "POLICY_DIR", data / "raw" / "policies"),
            csv_dir=env_path(env, "CSV_DIR", data / "raw" / "csv"), processed_dir=processed,
            employee_dataset_dir=env_path(env, "EMPLOYEE_DATASET_DIR", PROJECT_ROOT.parent / "data" / "KDN_Enterprise_AI_Dataset" / "KDN_Enterprise_AI_Dataset_Pexels"),
            employee_directory_dir=directory,
            employee_directory_db=env_path(env, 'EMPLOYEE_DIRECTORY_DB', directory / 'employee_directory.sqlite3'),
            chunks_dir=env_path(env, "CHUNKS_DIR", processed / "chunks"), vector_dir=vector,
            chroma_dir=env_path(env, "CHROMA_DIR", PROJECT_ROOT.parent / 'kdn_regulations_rag' / 'rag_data' / 'chroma_db'),
            sqlite_path=env_path(env, "SQLITE_PATH", data / "app.sqlite3"),
            sqlite_schema_path=env_path(env, 'SQLITE_SCHEMA_PATH', PROJECT_ROOT / 'database' / 'sqlite_schema.sql'),
            embedding_cache_dir=env_path(env, "EMBEDDING_CACHE_DIR", data / "models"),
            user_data_path=env_path(env, "USER_DATA_PATH", data / "raw" / "users.json"),
        )

    def policy_path(self, domain: str) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", domain):
            raise ValueError("분야 ID에는 소문자 영문·숫자·밑줄만 사용할 수 있습니다.")
        return self.policy_dir / domain

    def paths(self) -> dict[str, str]:
        """접속정보·비밀값을 제외한 경로만 반환합니다."""
        return {name: str(getattr(self, name)) for name in self.__dataclass_fields__ if isinstance(getattr(self, name), Path)}


settings = Settings.from_env()
