# WONIT 시스템 아키텍처

2026-11-06 프로젝트 코드와 로컬 설정을 기준으로 작성한 시스템 구성도입니다.

- `system-architecture.png`: 발표·보고서용 고해상도 이미지 (6,827 × 3,893)
- `system-architecture.svg`: 확대와 문구 수정이 가능한 벡터 원본
- `system-architecture-preview.png`: 화면 확인용 이미지 (1,920 × 1,095)

## 번호별 흐름

| 번호 | 연결 | 역할 |
| --- | --- | --- |
| 1 | 웹 브라우저 ↔ FastAPI | 질문·화면 요청, SSE 답변 수신 |
| 2 | FastAPI ↔ Ollama | 도구 선택용 JSON과 근거 기반 답변 생성 |
| 3 | FastAPI ↔ MCP 서버 | stdio로 업무 도구 호출, 조회·계산·검색 결과 반환 |
| 4 | MCP 서버 ↔ Chroma | BGE-M3로 질문 임베딩 후 규정 검색 |
| 5 | FastAPI ↔ 대화 DB | 세션·대화·평가 및 종료 이벤트 상태 저장·조회 |
| 6 | FastAPI → n8n → Google Sheets | 대화·평가 이벤트의 백그라운드 전송 및 시트 기록 |

사원·조직 SQLite는 FastAPI와 MCP가 조회합니다. 규정 PDF의 Docling 처리·청킹·임베딩·색인 적재는 별도 사전 구축 과정입니다. n8n에서 Google Sheets로 이어지는 경로는 워크플로 설정을 나타내며, 각 이벤트의 실제 저장 성공 여부는 실행 기록으로 확인해야 합니다.

현재 설정의 모델은 `gemma4:e2b`, 임베딩 모델은 `BAAI/bge-m3`입니다. 기술별 박스는 역할과 프로세스 경계를 표현하며, 별도 서버 배포를 뜻하지 않습니다.

## 수정 및 아이콘 출처

레이아웃과 문구는 `scripts/build_system_architecture.py`에서 생성합니다. SVG 안에 기술 아이콘을 포함해 외부 이미지 연결 없이 열 수 있습니다. 한글 글꼴은 맑은 고딕을 우선 사용합니다.

- 기술 아이콘: [Simple Icons v16](https://github.com/simple-icons/simple-icons/tree/16.0.0)
- 임베딩 생태계 아이콘: [Hugging Face](https://huggingface.co/)
- 벡터 DB 로고: [Chroma](https://www.trychroma.com/)
- 개별 이미지 주소: `icon-sources.json`

Hugging Face 아이콘은 Sentence Transformers/BGE-M3 설명을 위한 표식입니다. 실행은 로컬에서 이루어집니다.
