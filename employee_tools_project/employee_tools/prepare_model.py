"""최초 1회 BGE-M3를 프로젝트 내부 models/bge-m3에 준비합니다."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import sqlite3

from .common import ToolError
from .paths import configure_model_cache, embedding_model_path, rag_data_path


def read_embedding_metadata() -> dict:
    database = rag_data_path() / "chroma_db/chroma.sqlite3"
    if not database.is_file():
        raise ToolError("RAG_DB_NOT_FOUND", "프로젝트 내부 규정 DB가 없습니다.")
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT m.key, m.str_value, m.int_value FROM collection_metadata AS m "
            "JOIN collections AS c ON c.id = m.collection_id WHERE c.name = ?",
            ("kdn_regulations_bge_m3_v1",),
        ).fetchall()
    values = {key: string if string is not None else integer for key, string, integer in rows}
    if not values.get("embedding_model") or not values.get("embedding_revision") or values["embedding_revision"] == "unknown":
        raise ToolError("MODEL_METADATA_ERROR", "규정 DB의 모델·개정본 정보를 확인하세요.")
    return values


def select_model_files(names: list[str]) -> list[str]:
    """dense SentenceTransformer에 필요한 파일만 선택합니다. 원격 Python은 받지 않습니다."""
    roots = {"config.json", "config_sentence_transformers.json", "modules.json", "sentence_bert_config.json",
             "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "sentencepiece.bpe.model",
             "vocab.json", "vocab.txt", "merges.txt", "added_tokens.json", "README.md", "LICENSE", "LICENSE.txt"}
    weights = "model.safetensors" if "model.safetensors" in names else "pytorch_model.bin"
    if weights not in names:
        raise ToolError("MODEL_FILES_ERROR", "지원하는 dense 모델 가중치 파일이 없습니다.")
    selected = [name for name in names if name in roots or name == weights or name.startswith("1_Pooling/")]
    for name in selected:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.suffix == ".py":
            raise ToolError("MODEL_FILES_ERROR", "허용되지 않은 모델 파일 경로입니다.")
    return sorted(selected)


def prepare_model() -> dict:
    metadata = read_embedding_metadata()
    configure_model_cache()
    destination = embedding_model_path()
    try:
        ready = json.loads((destination / "model_manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ready = None
    if isinstance(ready, dict) and ready.get("model_name") == metadata["embedding_model"] and ready.get("revision") == metadata["embedding_revision"]:
        files = ready.get("files")
        if isinstance(files, list) and files and all(
            isinstance(name, str) and not PurePosixPath(name).is_absolute()
            and ".." not in PurePosixPath(name).parts and "\\" not in name
            and (destination / name).is_file() for name in files
        ):
            return ready
    from huggingface_hub import HfApi, snapshot_download

    model_name, revision = metadata["embedding_model"], metadata["embedding_revision"]
    try:
        info = HfApi(token=False).model_info(model_name, revision=revision, files_metadata=True)
    except Exception as exc:
        raise ToolError("MODEL_DOWNLOAD_ERROR", "모델 정보를 받지 못했습니다. 인터넷 연결을 확인하고 다시 실행하세요.") from exc
    selected = select_model_files([item.rfilename for item in info.siblings])
    destination = embedding_model_path()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(repo_id=model_name, revision=revision, local_dir=str(destination),
                          allow_patterns=selected, token=False)
    except Exception as exc:
        raise ToolError("MODEL_DOWNLOAD_ERROR", "모델 다운로드가 중단되었습니다. 같은 명령을 다시 실행하면 내부 폴더에서 이어받습니다.") from exc
    missing = [name for name in selected if not (destination / name).is_file()]
    if missing:
        raise ToolError("MODEL_DOWNLOAD_INCOMPLETE", "모델 다운로드가 끝나지 않았습니다. 다시 실행하세요.")
    manifest = {"model_name": model_name, "revision": revision,
                "embedding_dimension": metadata.get("embedding_dimension"), "files": selected}
    (destination / "model_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    try:
        manifest = prepare_model()
    except (ToolError, ImportError, OSError, ValueError) as exc:
        raise SystemExit(f"모델 준비 실패: {exc}") from exc
    print(f"모델 준비 완료: models/bge-m3 ({manifest['revision']})")


if __name__ == "__main__":
    main()
