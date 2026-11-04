# 규정 PDF 일괄 수집 → Chroma 저장

입력 ZIP이나 폴더의 모든 PDF를 순차 처리합니다. 특정 규정 이름이나 파일 개수를 코드에 고정하지 않았습니다. 실제 처리 대상은 실행 시 `inventory.json`에서 확인할 수 있습니다.

처리 흐름: PDF 탐색/압축 해제 → Docling 레이아웃·한국어 OCR·표 분석 → 구조화 JSON 저장 → HybridChunker → SentenceTransformer의 BAAI/bge-m3 → Chroma 영구 저장.

## 1. 준비

Python 3.11 이상을 사용하세요. 압축을 푼 이 코드 폴더에 원본 `한전KDN_59.zip`을 복사하세요. 원본 규정 파일은 코드 패키지에 포함되지 않았습니다.

PowerShell에서 이 코드 폴더를 열고 실행합니다.

```powershell
conda activate bigdata
python -m pip install -r requirements.txt
```

기존 환경의 패키지 버전을 고정해 업데이트할 수 있습니다. 현재 환경을 유지하려면 별도 가상환경을 사용하세요. GPU용 PyTorch 설치는 이 requirements에서 별도로 지정하지 않습니다.

## 2. 처리할 PDF 목록 확인

```powershell
python ingest_regulations.py --input ".\한전KDN_59.zip" --list-files
```

이 단계는 압축 속 PDF만 추출하고 목록을 저장합니다. 모델 다운로드·임베딩·DB 변경은 하지 않습니다. ZIP 내부의 ZIP은 펼치지 않습니다. PDF 이외의 HWP, DOCX, XLSX 등은 처리 대상에서 제외됩니다.

구형 ZIP에서 한글 파일명이 깨지면 `--zip-encoding cp949`를 추가하세요. UTF-8로 표시된 ZIP 항목은 Python이 해당 표시를 따릅니다.

## 3. PDF 전체 처리

```powershell
python ingest_regulations.py --input ".\한전KDN_59.zip"
```

ZIP 경로를 생략하면 스크립트와 같은 폴더의 `한전KDN_59.zip`을 찾습니다. 모든 경로는 공백이 있을 때 큰따옴표로 감싸세요.

이미 압축을 푼 PDF 폴더도 지정할 수 있습니다. 하위 폴더까지 검색합니다.

```powershell
python ingest_regulations.py --input "C:\cykim\workspace_bigdata\regulations"
```

`--workdir`는 PDF 입력 폴더 바깥으로 지정해야 합니다. 스크립트와 입력 PDF를 같은 폴더에 모두 두는 경우, 결과 폴더를 따로 지정하세요.

```powershell
python ingest_regulations.py --input ".\pdfs" --workdir ".\rag_data"
```

먼저 한 문서만 확인하려면 다음처럼 실행합니다. 이후 `--limit` 없이 재실행하면 완료된 문서는 건너뛰고 나머지를 처리합니다.

```powershell
python ingest_regulations.py --input ".\한전KDN_59.zip" --limit 1
```

## 4. OCR·장치 설정

| 옵션 | 동작 |
|---|---|
| `--ocr auto` | 기본값. EasyOCR의 한국어·영어 모델 사용. Docling이 OCR 대상으로 판단한 영역을 인식 |
| `--ocr off` | PDF 내부 텍스트만 추출. 문자가 정상적으로 선택되는 PDF에서 우선 비교 가능 |
| `--ocr full` | 모든 페이지를 OCR. 스캔 PDF 또는 문자층이 깨진 PDF에서 원문과 비교 |
| `--embedding-device cpu` | 기본값. CPU에서 임베딩 |
| `--embedding-device cuda` | CUDA PyTorch가 설치된 GPU에서 임베딩 |
| `--docling-device cpu` | 기본값. Docling과 EasyOCR는 CPU 사용 |
| `--max-tokens 512` | 문서명·제목 문맥을 포함한 청크 목표 길이 |
| `--batch-size 8` | 임베딩 배치. GPU 메모리가 부족하면 2 또는 1로 감소 |

GPU 임베딩 예시:

```powershell
python ingest_regulations.py --input ".\한전KDN_59.zip" --embedding-device cuda --batch-size 4
```

첫 실행에는 Docling·EasyOCR·BGE-M3 모델 다운로드가 필요할 수 있습니다. 인터넷이 차단된 환경에서는 필요한 모델을 먼저 준비해야 합니다. 이 코드는 외부 LLM API를 사용하지 않습니다. CPU/GPU의 실제 처리 시간과 전체 규정의 추출 정확도는 측정하지 않았습니다.

`auto`는 OCR 결과의 정확성을 보장하지 않습니다. `review.json`의 청크가 없는 페이지, `tables.html`의 숫자·단위·병합 셀·주석을 원본과 비교하세요.

## 5. 저장 결과

기본 결과 폴더는 **스크립트 폴더/rag_data**입니다.

| 경로 | 내용 |
|---|---|
| `chroma_db/` | Chroma 영구 DB, 프로그램 재실행 후에도 유지 |
| `input_pdfs/` | ZIP에서 추출한 PDF. 실제 파일명 대신 안전한 해시 파일명 사용 |
| `inventory.json` | 원래 ZIP 상대 경로와 추출 PDF 경로의 연결 |
| `parsed/문서ID/document.json` | Docling 구조화 결과. 전체 표·좌표·부모 관계 확인 |
| `parsed/문서ID/document.md` | 사람이 읽기 위한 문서 추출 결과 |
| `parsed/문서ID/tables.html` | 병합 셀을 포함한 표 검토용 HTML |
| `parsed/문서ID/chunks.jsonl` | 임베딩한 `text`, 원래 청크 `raw_text`, 메타데이터 |
| `parsed/문서ID/review.json` | 목표 길이 초과 청크 및 검토할 페이지 |
| `manifest.json` | 문서별 처리 상태·원본 해시·캐시 정보 |
| `summary.json` | 이번 실행의 성공·건너뜀·실패 목록 |
| `run.log` | 실행 로그와 오류의 상세 원인 |

Chroma 컬렉션 기본 이름은 `kdn_regulations_bge_m3_v1`입니다. 각 청크에 원래 파일명, 상대 경로, PDF 페이지, 제목, Docling 요소 참조, 표 참조, PDF SHA-256, 토큰 수를 저장합니다. 목록 메타데이터는 JSON 문자열이며 `json.loads()`로 복원합니다. PDF 페이지는 파일의 실제 페이지 번호입니다. 인쇄된 페이지 번호·시행일·개정일은 자동으로 추정하지 않습니다.

`tables.html`은 검토용입니다. 이를 다시 임베딩하지 않으므로 동일 표를 HTML과 본문으로 이중 등록하지 않습니다. 표는 DoclingDocument에서 HybridChunker를 통해 검색용 텍스트로 직렬화합니다.

## 6. 검색 확인

수집과 같은 `--workdir`, `--collection`, `--dataset`, 모델 설정을 사용해야 합니다.

```powershell
python ingest_regulations.py --query "국내 출장 시 숙박비 지급 기준은 무엇인가요?"
```

```powershell
python ingest_regulations.py --query "경조휴가 사용 조건은 무엇인가요?" --top-k 5
```

결과는 관련 청크와 원본 PDF 페이지이며, LLM의 최종 답변을 생성하는 코드는 포함하지 않았습니다. 코사인 거리는 작을수록 가깝고 정확도나 정답 확률이 아닙니다. BGE-M3의 dense embedding만 사용합니다. BM25·리랭커·법적 적용 판단은 별도 기능입니다.

## 7. 재실행·오류 복구

- 완료된 문서는 원본 해시·설정·DB에 저장된 ID와 처리 서명을 확인해 건너뜁니다.
- 원본 PDF가 달라지거나 OCR/청크 설정이 달라지면 해당 문서를 다시 처리합니다.
- PDF 변환 캐시가 같으면 재사용합니다. 기존 캐시를 사용해 강제로 재임베딩하려면 `--force`를 추가하세요.
- PDF부터 다시 분석하려면 `--reparse`를 추가하세요. OCR 옵션을 바꾸면 캐시 서명이 달라져 자동으로 재분석합니다.
- 한 PDF가 실패하면 로그에 남기고 다음 파일을 계속 처리합니다. 일부 실패 또는 시작 단계 실패가 있으면 종료 코드는 1입니다. `summary.json`과 `run.log`를 확인하고 재실행하세요.
- Docling이 부분 성공을 반환한 문서는 정상 완료로 간주하지 않습니다.
- 목표 512토큰을 넘는 표 행은 `review.json`에 남깁니다. 임베딩 모델 한도 안이면 전체 내용을 임베딩하며, 모델 한도를 넘으면 해당 문서는 실패 처리합니다. 텍스트를 조용히 잘라 저장하지 않습니다.
- 동일 문서는 `upsert`로 갱신합니다. 새 임베딩을 모두 계산한 뒤 저장하고, 저장에 성공한 문서의 이전 청크 중 더 이상 없는 ID만 제거합니다. 문서 자체가 입력에서 사라졌을 때 DB에서 자동 삭제하지는 않습니다.
- 같은 파일명을 가진 서로 다른 하위 폴더의 PDF도 별도 문서로 구분합니다. 입력 ZIP/폴더의 내부 상대 경로를 바꾸면 다른 문서로 인식합니다.
- 임베딩 모델·모델 개정본·벡터 차원이 다른 기존 컬렉션은 재사용하지 않습니다. 다른 모델을 쓰려면 새 `--collection`을 지정하세요. 로컬 모델에 해석 가능한 개정 식별자가 없으면 `unknown`으로 기록되므로 모델 파일 변경 시 새 컬렉션을 사용하세요.
- 이 예제는 문서 한 개 전체를 DB 트랜잭션으로 교체하지 않습니다. 저장 도중 중단되면 재실행해 복구하세요. 수집 중에는 검색 서비스를 함께 운영하지 않는 개발용 구성을 권장합니다.
- `ingestion.lock`은 같은 작업 폴더에서 동시 수집을 막습니다. 강제 종료 후 남았다면 다른 수집 프로세스가 종료된 것을 확인한 뒤 이 파일만 삭제하세요.

## 8. 검증 범위

`VALIDATION.md`를 확인하세요. 테스트용 임베딩으로 DB 동작을 검증한 것과 실제 BGE-M3 추론·문서 추출 품질 검증을 구분합니다. 첨부 ZIP의 실제 PDF 개수와 전체 변환 결과는 실행 전 확정하지 않았습니다.

## 참고

- [Docling 변환 설정](https://docling-project.github.io/docling/_generated/examples/custom_convert/)
- [Docling HybridChunker](https://docling-project.github.io/docling/concepts/chunking/)
- [BGE-M3 모델](https://huggingface.co/BAAI/bge-m3)
- [Chroma upsert](https://docs.trychroma.com/docs/collections/update-data)
