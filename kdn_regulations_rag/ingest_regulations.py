"""PDF/ZIP -> Docling -> HybridChunker -> SentenceTransformer -> local Chroma.

Examples (PowerShell, from this file's directory):
    python ingest_regulations.py --input ".\한전KDN_59.zip" --list-files
    python ingest_regulations.py --input ".\한전KDN_59.zip"
    python ingest_regulations.py --query "국내 출장 숙박비 지급 기준은?"

Python 3.11+ recommended. Install requirements.txt first.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import gc
import hashlib
import html
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
from typing import Any
import unicodedata
import zipfile
import zlib


BASE_DIR = Path(__file__).resolve().parent
PIPELINE_VERSION = "1"
LOGGER = logging.getLogger("regulations")


@dataclass(frozen=True)
class PdfSource:
    path: Path
    relative_name: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def matches_zip_entry(path: Path, entry: zipfile.ZipInfo) -> bool:
    """Validate cached named PDFs even when a new revision has the same size."""
    if not path.is_file() or path.stat().st_size != entry.file_size:
        return False
    checksum = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum = zlib.crc32(block, checksum)
    return (checksum & 0xFFFFFFFF) == entry.CRC


def signature(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


@contextmanager
def ingestion_lock(workdir: Path):
    """Protect this working directory against simultaneous ingestion runs."""
    lock = workdir / "ingestion.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError(
            f"이미 작업 중이거나 이전 작업의 잠금 파일이 있습니다: {lock}\n"
            "다른 수집 프로세스가 종료된 것을 확인한 뒤 잠금 파일을 삭제하세요."
        ) from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}, stream)
        yield
    finally:
        lock.unlink(missing_ok=True)


def discover_sources(input_path: Path, workdir: Path, zip_encoding: str | None) -> list[PdfSource]:
    """Discover PDFs recursively; preserve validated ZIP folder/file names."""
    if input_path.is_dir():
        # Prevent subsequent runs from recursively ingesting our extracted/cache PDFs.
        if workdir == input_path or workdir.is_relative_to(input_path):
            raise ValueError("--workdir는 PDF 입력 폴더 바깥으로 지정하세요.")
        sources = [
            PdfSource(path.resolve(), path.relative_to(input_path).as_posix())
            for path in input_path.rglob("*")
            if path.is_file() and path.suffix.lower() == ".pdf"
        ]
    elif input_path.is_file() and input_path.suffix.lower() == ".pdf":
        sources = [PdfSource(input_path, input_path.name)]
    elif input_path.is_file() and input_path.suffix.lower() == ".zip":
        extraction = (workdir / "input_pdfs").resolve()
        if not extraction.is_relative_to(workdir.resolve()):
            raise ValueError("input_pdfs가 작업 폴더 바깥을 가리킵니다.")
        sources = []
        seen = set()
        with zipfile.ZipFile(input_path, metadata_encoding=zip_encoding) as archive:
            entries = sorted(archive.infolist(), key=lambda item: item.filename.casefold())
            pdf_entries = [
                item for item in entries
                if not item.is_dir() and item.filename.lower().endswith(".pdf")
                and not item.filename.replace("\\", "/").startswith("__MACOSX/")
            ]
            if sum(item.file_size for item in pdf_entries) > 4 * 1024**3:
                raise ValueError("ZIP 내 PDF의 압축 해제 크기가 4 GiB를 넘습니다. 폴더로 해제해 입력하세요.")
            for item in pdf_entries:
                relative = PurePosixPath(item.filename.replace("\\", "/"))
                if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
                    raise ValueError(f"허용하지 않는 ZIP 경로입니다: {item.filename}")
                normalized = unicodedata.normalize("NFC", relative.as_posix())
                if normalized.casefold() in seen:
                    raise ValueError(f"중복 ZIP PDF 경로입니다: {normalized}")
                seen.add(normalized.casefold())
                # Preserve the archive path after checking that it stays inside input_pdfs.
                destination = (extraction / Path(*PurePosixPath(normalized).parts)).resolve()
                if not destination.is_relative_to(extraction):
                    raise ValueError(f"추출 폴더 바깥을 가리키는 ZIP 경로입니다: {normalized}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not matches_zip_entry(destination, item):
                    temporary = destination.with_suffix(".pdf.tmp")
                    with archive.open(item) as source, temporary.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    temporary.replace(destination)
                sources.append(PdfSource(destination, normalized))
    else:
        raise FileNotFoundError(f"PDF, ZIP 또는 폴더를 찾을 수 없습니다: {input_path}")
    sources.sort(key=lambda source: source.relative_name.casefold())
    if not sources:
        raise ValueError("입력에서 PDF를 찾지 못했습니다. ZIP 안의 다른 ZIP은 펼치지 않습니다.")
    names = [unicodedata.normalize("NFC", source.relative_name).casefold() for source in sources]
    if len(names) != len(set(names)):
        raise ValueError("대소문자 또는 유니코드 정규화 후 중복되는 PDF 경로가 있습니다.")
    return sources


def make_converter(args):
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice(args.docling_device), num_threads=args.cpu_threads,
    )
    options.do_table_structure = True
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    options.table_structure_options.do_cell_matching = True
    options.do_ocr = args.ocr != "off"
    if options.do_ocr:
        options.ocr_options = EasyOcrOptions(
            lang=["ko", "en"],
            use_gpu=args.docling_device == "cuda",
            force_full_page_ocr=args.ocr == "full",
        )
    if args.timeout is not None:
        options.document_timeout = args.timeout
    # Run inference locally; external model-service calls stay disabled.
    options.enable_remote_services = False
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def load_embedding_model(args):
    from sentence_transformers import SentenceTransformer

    kwargs = {"device": args.embedding_device}
    if args.model_revision:
        kwargs["revision"] = args.model_revision
    model = SentenceTransformer(args.embedding_model, **kwargs)
    if args.max_tokens > model.max_seq_length:
        raise ValueError(f"--max-tokens가 모델 입력 한도({model.max_seq_length})를 넘습니다.")
    # Record a resolved Hub commit when available, to prevent mixing model revisions.
    first_module = model._first_module()
    configuration = getattr(getattr(first_module, "auto_model", None), "config", None)
    resolved_revision = getattr(configuration, "_commit_hash", None) or args.model_revision or "unknown"
    model_metadata = {
        "embedding_model": args.embedding_model,
        "embedding_revision": str(resolved_revision),
        "embedding_dimension": int(model.get_sentence_embedding_dimension()),
        "normalized_embeddings": True,
    }
    return model, model_metadata


def open_collection(args, model_metadata: dict, create: bool):
    import chromadb

    database_path = args.workdir / "chroma_db"
    if not create and not database_path.is_dir():
        raise FileNotFoundError(f"먼저 문서를 수집하세요. DB가 없습니다: {database_path}")
    client = chromadb.PersistentClient(path=str(database_path))
    if create:
        collection = client.get_or_create_collection(
            name=args.collection, embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}}, metadata=model_metadata,
        )
    else:
        collection = client.get_collection(name=args.collection, embedding_function=None)
    if any((collection.metadata or {}).get(key) != value for key, value in model_metadata.items()):
        raise ValueError("컬렉션의 임베딩 모델/개정본/차원이 다릅니다. 다른 --collection 이름을 사용하세요.")
    if collection.configuration["hnsw"]["space"] != "cosine":
        raise ValueError("기존 컬렉션의 거리 함수가 cosine이 아닙니다. 다른 컬렉션 이름을 사용하세요.")
    return client, collection


def load_or_convert(source: PdfSource, output: Path, parse_signature: str, converter, reparse: bool):
    from docling.datamodel.base_models import ConversionStatus
    from docling_core.types.doc import DoclingDocument

    document_path = output / "document.json"
    cache_metadata = read_json(output / "parse_state.json", {})
    if not reparse and cache_metadata.get("signature") == parse_signature and document_path.is_file():
        LOGGER.info("  저장된 Docling JSON 재사용")
        return DoclingDocument.load_from_json(document_path)

    LOGGER.info("  PDF 읽기 / 레이아웃·표·OCR 분석")
    result = converter.convert(source.path, raises_on_error=False)
    if result.status != ConversionStatus.SUCCESS:
        raise RuntimeError(f"Docling 변환 미완료: {result.status}; {result.errors}")
    document = result.document
    write_json(document_path, document.export_to_dict())
    write_json(output / "parse_state.json", {"signature": parse_signature})
    return document


def export_review_files(document, output: Path, source: PdfSource) -> list[str]:
    """Keep structured JSON/HTML as review material; index tables only once."""
    warnings = []
    try:
        atomic_text(output / "document.md", document.export_to_markdown())
        tables = ["<!doctype html><html lang='ko'><meta charset='utf-8'><body>",
                  f"<h1>{html.escape(source.relative_name)}</h1>"]
        for index, table in enumerate(document.tables, 1):
            pages = sorted({prov.page_no for prov in (table.prov or [])})
            tables.append(f"<h2>표 {index} / PDF 페이지 {pages}</h2>")
            tables.append(table.export_to_html(doc=document))
        tables.append("</body></html>")
        atomic_text(output / "tables.html", "\n".join(tables))
    except Exception as error:
        warnings.append(f"검토용 Markdown/HTML 내보내기 실패: {error}")
    return warnings


def make_records(document, source: PdfSource, document_id: str, source_hash: str,
                 index_signature: str, args, model):
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

    prefix = f"문서: {PurePosixPath(source.relative_name).stem}\n"
    prefix_tokens = len(model.tokenizer.encode(prefix, add_special_tokens=False))
    budget = args.max_tokens - prefix_tokens - model.tokenizer.num_special_tokens_to_add(pair=False) - 8
    if budget < 32:
        raise ValueError("문서명에 비해 --max-tokens가 너무 작습니다.")
    chunker = HybridChunker(
        tokenizer=HuggingFaceTokenizer(tokenizer=model.tokenizer, max_tokens=budget),
        merge_peers=False, repeat_table_header=True, omit_header_on_overflow=False,
    )
    records = []
    for chunk in chunker.chunk(dl_doc=document):
        contextual_text = chunker.contextualize(chunk=chunk).strip()
        if not contextual_text:
            continue
        text = prefix + contextual_text
        items = chunk.meta.doc_items or []
        pages = sorted({prov.page_no for item in items for prov in (item.prov or [])})
        refs = list(dict.fromkeys(item.self_ref for item in items))
        token_count = len(model.tokenizer.encode(text, add_special_tokens=True, truncation=False))
        metadata = {
            "dataset": args.dataset,
            "document_id": document_id,
            "source": PurePosixPath(source.relative_name).name,
            "source_relative_path": source.relative_name,
            "source_sha256": source_hash,
            "index_signature": index_signature,
            "pdf_pages_json": json.dumps(pages),
            "headings_json": json.dumps(chunk.meta.headings or [], ensure_ascii=False),
            "source_refs_json": json.dumps(refs, ensure_ascii=False),
            "table_refs_json": json.dumps([ref for ref in refs if ref.startswith("#/tables/")]),
            "token_count": token_count,
            "over_target": token_count > args.max_tokens,
        }
        records.append({"id": f"{document_id}:{len(records) + 1:06d}",
                        "text": text, "raw_text": chunk.text, "metadata": metadata})
    if not records:
        raise ValueError("추출된 검색용 청크가 없습니다. OCR 설정과 원문을 확인하세요.")
    return records


def save_to_chroma(records: list[dict], model, client, collection, document_id: str, batch_size: int):
    import numpy as np

    texts = [record["text"] for record in records]
    vectors = model.encode(texts, batch_size=batch_size, show_progress_bar=True,
                           convert_to_numpy=True, normalize_embeddings=True)
    vectors = np.asarray(vectors, dtype=np.float32)
    expected_dimension = int(model.get_sentence_embedding_dimension())
    if vectors.shape != (len(records), expected_dimension) or not np.isfinite(vectors).all():
        raise ValueError(f"임베딩 결과가 올바르지 않습니다: {vectors.shape}")
    write_batch = min(128, client.get_max_batch_size())
    for start in range(0, len(records), write_batch):
        end = start + write_batch
        collection.upsert(
            ids=[record["id"] for record in records[start:end]],
            documents=texts[start:end], embeddings=vectors[start:end].tolist(),
            metadatas=[record["metadata"] for record in records[start:end]],
        )
    # Delete only obsolete chunks belonging to this successfully processed document.
    existing = collection.get(where={"document_id": document_id}, include=[])["ids"]
    stale = sorted(set(existing) - {record["id"] for record in records})
    for start in range(0, len(stale), write_batch):
        collection.delete(ids=stale[start:start + write_batch])
    saved_ids = collection.get(where={"document_id": document_id}, include=[])["ids"]
    if set(saved_ids) != {record["id"] for record in records}:
        raise RuntimeError("저장 후 문서별 청크 ID 검증에 실패했습니다.")


def can_skip(previous: dict, index_signature: str, document_id: str, collection) -> bool:
    if previous.get("status") != "success" or previous.get("index_signature") != index_signature:
        return False
    stored = collection.get(where={"document_id": document_id}, include=["metadatas"])
    expected_ids = {f"{document_id}:{index + 1:06d}" for index in range(previous["chunk_count"])}
    return (set(stored["ids"]) == expected_ids and bool(expected_ids)
            and all(meta.get("index_signature") == index_signature for meta in stored["metadatas"]))


def parsed_output_path(workdir: Path, source: PdfSource) -> Path:
    """Use the original PDF's relative path and title for reviewable artifacts."""
    root = (workdir / "parsed").resolve()
    relative = PurePosixPath(source.relative_name).with_suffix("")
    output = root.joinpath(*relative.parts).resolve()
    if output == root or not output.is_relative_to(root):
        raise ValueError(f"parsed 폴더 바깥을 가리키는 문서 경로입니다: {source.relative_name}")
    return output


def prepare_parsed_directory(workdir: Path, document_id: str, output: Path) -> None:
    """Rename an old hash cache within parsed; never overwrite an existing target."""
    root = (workdir / "parsed").resolve()
    legacy = (root / document_id).resolve()
    if output == root or not output.is_relative_to(root) or not legacy.is_relative_to(root):
        raise ValueError("변환 결과 폴더의 이동 경로가 parsed 폴더 바깥입니다.")
    if legacy != output and legacy.is_dir() and not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        # Both resolved absolute paths were checked against the same parsed root.
        legacy.rename(output)
        LOGGER.info("  기존 변환 폴더 이름 변경: %s -> %s", document_id, output.relative_to(root))
    output.mkdir(parents=True, exist_ok=True)


def run_ingestion(args, sources: list[PdfSource]) -> int:
    model, model_metadata = load_embedding_model(args)
    client, collection = open_collection(args, model_metadata, create=True)
    converter = None  # Initialize lazily: a completed repeat run does not load Docling models.
    versions = {name: version(name) for name in ("docling", "docling-core", "sentence-transformers", "chromadb")}
    parser_options = {"ocr": args.ocr, "table_mode": "accurate", "versions": versions,
                      "pipeline_version": PIPELINE_VERSION}
    manifest_path = args.workdir / "manifest.json"
    manifest = read_json(manifest_path, {"documents": {}})
    outcomes = []
    for number, source in enumerate(sources, 1):
        LOGGER.info("[%s/%s] %s", number, len(sources), source.relative_name)
        document_id = signature({"dataset": args.dataset, "source": source.relative_name})[:24]
        manifest_key = f"{args.collection}/{document_id}"
        output = parsed_output_path(args.workdir, source)
        entry = {"document_id": document_id, "source": source.relative_name,
                 "source_local_path": str(source.path), "collection": args.collection,
                 "updated_at": datetime.now(timezone.utc).isoformat(), "parsed_directory": str(output)}
        try:
            prepare_parsed_directory(args.workdir, document_id, output)
            source_hash = sha256_file(source.path)
            parse_signature = signature({"pdf_sha256": source_hash, **parser_options})
            index_signature = signature({"parse_signature": parse_signature, "model": model_metadata,
                                         "max_tokens": args.max_tokens, "merge_peers": False,
                                         "repeat_table_header": True, "prefix_version": 1})
            previous = manifest["documents"].get(manifest_key, {})
            if (not args.force and not args.reparse and (output / "document.json").is_file()
                    and can_skip(previous, index_signature, document_id, collection)):
                LOGGER.info("  완료된 문서 건너뜀: %s개 청크", previous["chunk_count"])
                previous = {**previous, **entry}
                manifest["documents"][manifest_key] = previous
                write_json(manifest_path, manifest)
                outcomes.append({**previous, "run_status": "skipped"})
                continue
            if converter is None:
                converter = make_converter(args)
            document = load_or_convert(source, output, parse_signature, converter, args.reparse)
            warnings = export_review_files(document, output, source)
            records = make_records(document, source, document_id, source_hash, index_signature, args, model)
            atomic_text(output / "chunks.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records))
            overflow = [row for row in records if row["metadata"]["over_target"]]
            pages_with_chunks = {page for row in records for page in json.loads(row["metadata"]["pdf_pages_json"])}
            pages_without_chunks = sorted(set(document.pages) - pages_with_chunks)
            if pages_without_chunks:
                warnings.append(f"검색 청크에 연결되지 않은 PDF 페이지: {pages_without_chunks} (빈 페이지/이미지/추출 누락 확인)")
            if overflow:
                warnings.append(f"목표 {args.max_tokens}토큰을 넘은 청크: {len(overflow)}개. 내용을 자르지 않고 보존합니다.")
            write_json(output / "review.json", {"warnings": warnings, "over_target_chunks": overflow,
                       "pdf_page_count": len(document.pages), "table_count": len(document.tables)})
            hard_overflow = [row["id"] for row in records if row["metadata"]["token_count"] > model.max_seq_length]
            if hard_overflow:
                raise ValueError(f"모델 입력 한도 {model.max_seq_length} 초과. chunks.jsonl에서 확인: {hard_overflow[:5]}")
            LOGGER.info("  임베딩 / Chroma 저장: %s개 청크", len(records))
            save_to_chroma(records, model, client, collection, document_id, args.batch_size)
            entry.update(status="success", index_signature=index_signature, source_sha256=source_hash,
                         chunk_count=len(records), page_count=len(document.pages),
                         table_count=len(document.tables), warnings=warnings, parsed_directory=str(output))
            outcomes.append({**entry, "run_status": "indexed"})
            for warning in warnings:
                LOGGER.warning("  %s", warning)
            del document, records
            gc.collect()
        except Exception as error:
            LOGGER.exception("  처리 실패; 다음 PDF로 진행합니다")
            entry.update(status="failed", error=f"{type(error).__name__}: {error}")
            outcomes.append({**entry, "run_status": "failed"})
        manifest["documents"][manifest_key] = entry
        write_json(manifest_path, manifest)
    summary = {"finished_at": datetime.now(timezone.utc).isoformat(), "versions": versions,
               "collection": args.collection, "dataset": args.dataset,
               "found_pdf_count": len(sources),
               "indexed_pdf_count": sum(row["run_status"] == "indexed" for row in outcomes),
               "skipped_pdf_count": sum(row["run_status"] == "skipped" for row in outcomes),
               "failed_pdf_count": sum(row["run_status"] == "failed" for row in outcomes),
               "collection_chunk_count": collection.count(), "documents": outcomes}
    write_json(args.workdir / "summary.json", summary)
    LOGGER.info("완료: 신규/갱신 %s, 건너뜀 %s, 실패 %s / 전체 컬렉션 %s개 청크",
                summary["indexed_pdf_count"], summary["skipped_pdf_count"],
                summary["failed_pdf_count"], summary["collection_chunk_count"])
    return 1 if summary["failed_pdf_count"] else 0


def run_query(args) -> int:
    model, model_metadata = load_embedding_model(args)
    _, collection = open_collection(args, model_metadata, create=False)
    if collection.count() == 0:
        raise ValueError("컬렉션에 저장된 청크가 없습니다.")
    query_tokens = len(model.tokenizer.encode(args.query, add_special_tokens=True, truncation=False))
    if query_tokens > model.max_seq_length:
        raise ValueError("질문이 임베딩 모델의 입력 한도를 넘습니다.")
    vector = model.encode([args.query], convert_to_numpy=True, normalize_embeddings=True)
    result = collection.query(query_embeddings=vector.tolist(), where={"dataset": args.dataset},
                              n_results=min(args.top_k, collection.count()),
                              include=["documents", "metadatas", "distances"])
    for index, (text, metadata, distance) in enumerate(zip(result["documents"][0], result["metadatas"][0],
                                                         result["distances"][0]), 1):
        print(f"\n[{index}] {metadata['source_relative_path']}")
        print(f"PDF 페이지: {json.loads(metadata['pdf_pages_json'])}")
        print(f"코사인 거리: {distance:.4f} (작을수록 가까움)")
        print(text)
    if not result["ids"][0]:
        print("이 dataset에 해당하는 검색 결과가 없습니다.")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=BASE_DIR / "한전KDN_59.zip", help="ZIP, PDF 한 개 또는 PDF 폴더")
    parser.add_argument("--workdir", type=Path, default=BASE_DIR / "rag_data", help="결과 및 DB 폴더")
    parser.add_argument("--dataset", default="kdn-regulations", help="문서 집합의 고정 식별자")
    parser.add_argument("--collection", default="kdn_regulations_bge_m3_v1")
    parser.add_argument("--embedding-model", default="BAAI/bge-m3")
    parser.add_argument("--model-revision", default=None, help="선택: Hugging Face 모델 commit/tag")
    parser.add_argument("--embedding-device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--docling-device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--ocr", choices=["auto", "off", "full"], default="auto", help="auto=한/영 EasyOCR, off=PDF 문자만, full=전체 페이지 OCR")
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=None, help="선택: PDF 한 개의 변환 제한 시간(초)")
    parser.add_argument("--max-tokens", type=int, default=512, help="청크의 목표 토큰 수, 문서명/문맥 포함")
    parser.add_argument("--batch-size", type=int, default=8, help="임베딩 배치 크기")
    parser.add_argument("--zip-encoding", default=None, help="레거시 ZIP의 한글 파일명이 깨지면 cp949")
    parser.add_argument("--limit", type=int, default=None, help="처음 N개 PDF만 처리")
    parser.add_argument("--list-files", action="store_true", help="PDF 목록만 저장/출력; 모델 로딩과 DB 변경 없음")
    parser.add_argument("--force", action="store_true", help="완료 문서도 재임베딩; Docling 캐시는 재사용")
    parser.add_argument("--reparse", action="store_true", help="PDF 변환부터 다시 수행")
    parser.add_argument("--query", default=None, help="문서 수집 대신 저장된 DB 검색")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)
    if min(args.max_tokens, args.batch_size, args.cpu_threads, args.top_k) < 1:
        parser.error("토큰 수/배치 크기/스레드 수/top-k는 양수여야 합니다.")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit은 양수여야 합니다.")
    if args.timeout is not None and args.timeout <= 0:
        parser.error("--timeout은 양수여야 합니다.")
    args.input = args.input.expanduser().resolve()
    args.workdir = args.workdir.expanduser().resolve()
    return args


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    args.workdir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(args.workdir / "run.log", encoding="utf-8")])
    try:
        if args.query is not None:
            return run_query(args)
        with ingestion_lock(args.workdir):
            sources = discover_sources(args.input, args.workdir, args.zip_encoding)
            if args.limit:
                sources = sources[:args.limit]
            inventory = [{"source": source.relative_name, "local_pdf": str(source.path),
                          "size_bytes": source.path.stat().st_size} for source in sources]
            write_json(args.workdir / "inventory.json", inventory)
            LOGGER.info("처리 대상 PDF: %s개", len(sources))
            if args.list_files:
                for source in sources:
                    print(source.relative_name)
                return 0
            return run_ingestion(args, sources)
    except Exception:
        LOGGER.exception("작업을 완료하지 못했습니다")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
