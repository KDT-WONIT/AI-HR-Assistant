"""프로젝트 내부 파일 위치. 실행 위치나 PC 사용자 이름에 의존하지 않습니다."""
from __future__ import annotations

import os
from pathlib import Path

from .common import ToolError

# 압축 해제한 employee_tools_project 폴더입니다.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def project_path(default: str, value: str | Path | None = None) -> Path:
    """상대 경로는 프로젝트 기준으로 해석하고 폴더 밖 접근은 거부합니다."""
    root = PROJECT_ROOT.resolve()
    candidate = Path(value) if value is not None else Path(default)
    resolved = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ToolError("EXTERNAL_PATH_NOT_ALLOWED", "파일은 압축 해제한 프로젝트 폴더 내부에 있어야 합니다.")
    return resolved


def employee_db_path(value: str | Path | None = None) -> Path:
    return project_path("data/employee/employee.sqlite3", value)


def sql_queries_path(value: str | Path | None = None) -> Path:
    return project_path("employee_tools/sql_queries.json", value)


def rag_data_path(value: str | Path | None = None) -> Path:
    return project_path("data/rag_data", value)


def embedding_model_path() -> Path:
    return project_path("models/bge-m3")


def configure_model_cache() -> Path:
    """다운로드·추론 때 생성하는 모델 관련 캐시도 프로젝트 안에 둡니다."""
    runtime = project_path(".runtime")
    locations = {
        "HF_HOME": runtime / "huggingface",
        "HF_HUB_CACHE": runtime / "huggingface/hub",
        "HF_XET_CACHE": runtime / "huggingface/xet",
        "SENTENCE_TRANSFORMERS_HOME": runtime / "sentence_transformers",
        "TORCH_HOME": runtime / "torch",
        "XDG_CACHE_HOME": runtime / "cache",
    }
    for key, directory in locations.items():
        directory = project_path(".runtime", directory)
        directory.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(directory)
    os.environ["HF_TOKEN_PATH"] = str(runtime / "huggingface/token")
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    return runtime
