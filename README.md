# 사내 규정 AI 업무 도우미 (WONIT HR AI Assistant)

사내 규정과 인사 정보를 자연어로 물어볼 수 있는 로컬 챗봇입니다. 질문에 맞는 업무 도구를 AI가 골라 규정 검색·연차·출장비 계산·담당자 조회를 수행하고, 근거와 함께 답합니다.

![시스템 아키텍처](my-chatbot/docs/architecture/WONIT_HR_AI_Assistant_architecture.png)

## 주요 기능

- **규정 질의응답**: 9개 분야(인사·근로·급여·출장·조직·계약·보안·감사·연구)의 규정을 검색해 출처(문서·쪽)와 함께 답변합니다.
- **개인 맞춤 계산**: 입사일·직급 기준 연차 부여일수와 잔여 연차, 출장 예상 여비(계산 과정·규정 포함)를 계산합니다.
- **담당자·사원 찾기**: 답변 근거가 부족하면 관련 부서 담당자를 카드로 추천하고, 사원·부서 검색과 프로필 사진 조회를 제공합니다.
- **일반 대화**: 업무와 무관한 질문은 규정 검색 없이 자연스럽게 답합니다.
- **이력·평가·로그**: 대화는 SQLite에 저장하고, 만족도(1~5점)와 함께 n8n을 거쳐 Google Sheets에 기록합니다.

## 동작 흐름

질문 → 프로필·최근 대화 조회 → AI가 도구 선택 → MCP 도구 실행(규정 검색·데이터 조회·계산) → 근거 확인 후 답변 생성 → 저장·화면 표시

## 기술 스택

| 영역 | 사용 기술 |
| --- | --- |
| 화면 | HTML · CSS · JavaScript (`frontend_v7`) |
| 서버 | Python 3.13 · FastAPI |
| AI 모델 | Ollama (`gemma4:e2b`, 도구 선택과 답변 생성 공용) |
| 도구 호출 | MCP (stdio) |
| 규정 검색(RAG) | ChromaDB · BAAI/bge-m3 임베딩 (59개 문서, 7,117개 조각) |
| 데이터 | SQLite (`data/app.sqlite3` 대화·평가·연차, `database/employee_directory` 사원·부서) |
| 로그 자동화 | n8n → Google Sheets |

## 실행

가상환경을 활성화한 뒤 `my-chatbot` 폴더에서 실행합니다. Ollama가 켜져 있어야 합니다.

```console
python -m pip install -r requirements.txt
python -m scripts.init_db
python -m app --reload
```

- 화면: http://127.0.0.1:8000/
- API 문서: http://127.0.0.1:8000/docs
- 사번은 `WON` 뒤에 숫자만 입력합니다(예: `0001`). 사원 데이터는 가상의 105명, 부서 16개입니다.
- 테스트: `python -m tests -v`

## 설정 (.env)

실제 값은 `.env`에 두고, 공유용 양식은 `.env.example`입니다. 자주 바꾸는 항목만 정리했습니다.

| 항목 | 설명 |
| --- | --- |
| `OLLAMA_MODEL` / `OLLAMA_ANSWER_MODEL` | 도구 선택 / 답변 생성 모델. 코드 기본값은 `qwen2.5:3b` / `gemma3:4b`, 현재 `.env`는 둘 다 `gemma4:e2b` |
| `UI_REGULATIONS_DIR` | 사내 규정 화면의 PDF 원문 폴더 (`./data/regulations_pdf`, 59개) |
| `CHROMA_DIR` | 규정 벡터 DB 위치 (`../kdn_regulations_rag/rag_data/chroma_db`) |
| `SQLITE_PATH` | 앱 DB (`./data/app.sqlite3`) |
| `EMPLOYEE_DIRECTORY_DIR` | 사원 DB (`./database/employee_directory`) |
| `ENABLED_TOOLS` | 비우면 전체 도구 사용, 쉼표로 ID를 적으면 일부만 사용 |
| `N8N_WEBHOOK_URL` | 로그를 보낼 n8n 주소. 비우면 전송하지 않으며 대화는 정상 동작 |
| `N8N_ASYNC` | 기본 `true`. 로그를 백그라운드로 보내 답변 속도에 영향이 없음 |

n8n으로 보내는 이벤트는 `session_start`, `question`, `answer`, `feedback`(만족도와 함께 종료), `end`(만족도 없이 종료) 5가지이며 이름은 `N8N_EVENT_*` 항목으로 바꿀 수 있습니다. 자세한 내용은 [docs/end-webhook.md](docs/end-webhook.md)를 참고하세요.

서로 다른 모델 두 개를 쓰는 경우에는 Ollama 서버의 `OLLAMA_MAX_LOADED_MODELS=2` 설정이 필요합니다. 같은 모델을 쓰면 필요 없습니다.

## 폴더 구조

| 위치 | 역할 |
| --- | --- |
| `app/agent` | 대화 처리, 도구 선택, 답변 생성 |
| `app/tools` · `app/mcp` | 분야별 도구와 MCP 서버·클라이언트 |
| `app/rag` | 임베딩과 ChromaDB 검색 |
| `app/repositories` | 대화·사원 데이터 접근 |
| `frontend_v7` | 현재 화면 (이전 화면은 `frontend`에 보존) |
| `database` · `data` | 사원 DB, 앱 DB, 평가 데이터 |
| `scripts` | DB 준비, 데이터 적재, 평가, ERD·명세 생성 |
| `tests` | 테스트 |

## 더 알아보기

- [시스템 구성도 설명](docs/architecture/README.md) · [DB 구조(ERD)](docs/erd)
- [계산기(연차·출장비)](docs/calculators.md) · [도구 호출 안전장치](docs/tool-calling-safeguards.md)
- [RAG 구성](docs/rag-sqlite.md) · [MCP](docs/mcp.md) · [답변 품질 기준](docs/answer-quality.md)
- [담당자 추천](docs/contact-escalation.md) · [사원 데이터](docs/employee-directory-integration.md)
- [발표 시나리오 검증 기록](docs/presentation-scenario-validation.md)
