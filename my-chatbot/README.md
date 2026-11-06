# 사내 규정 AI 업무 도우미

현재 화면은 **WONIT v7 UI**입니다. `frontend_v7`에서 기존 사원 DB·채팅·MCP·RAG·담당자 추천·이력·별점·n8n 기능을 연결합니다.
제공받은 원본 UI와 이전 `frontend`는 보존했습니다. [연결 기능·구현 이유·검증](docs/wonit-v7-integration.md)을 참고하세요.




SQLite 사원/대화 데이터, MCP 도구 서버·클라이언트, ChromaDB 규정 검색과 Ollama 답변을 연결한 로컬 앱입니다.



## 실행



가상환경을 활성화하고 my-chatbot 폴더에서 실행합니다.



```console

python -m pip install -r requirements.txt

python -m scripts.init_db

python -m app --reload

```



- 화면: http://127.0.0.1:8000/

- API 문서: http://127.0.0.1:8000/docs

- 사번 입력칸에는 `WON`이 고정으로 표시되고 숫자만 입력합니다(예: `0001`, `1234`). 시작할 때 사번은 비어 있습니다. database/employee_directory의 가상 사원 105명(기본 100명 + 발표용 팀원 5명)·부서 16개·연락처·업무 역할을 직접 조회합니다.

- 사원·부서 찾기에서 검색하고 프로필 사진을 확인할 수 있습니다. 사진은 로컬 파일 → 사원 DB의 사진 주소 → 로컬 아이콘 순서이며, 미리 받아두려면 `python -m scripts.download_employee_photos`를 실행합니다. 대화 기록은 기존 data/app.sqlite3에 보관합니다.

- Ollama 모델은 .env의 OLLAMA_MODEL(도구 선택)과 OLLAMA_ANSWER_MODEL(답변 생성)로 정합니다. 코드 기본값은 qwen2.5:3b / gemma3:4b이고, 현재 .env에는 gemma4:e2b가 지정되어 있습니다.

- 기존 chroma_db 컬렉션의 59개 문서 / 7,117개 조각을 사용합니다.

- BAAI/bge-m3 질문 임베딩은 원본 인덱스와 같은 리비전/1,024차원을 사용합니다.



## 동작



질문 → 사용자/최근 대화 조회 → MCP 도구 목록에서 Ollama가 하나 선택 → MCP 호출로 분야별 검색·조회/계산 → 컨텍스트 구성 → Ollama 답변 생성 → SQLite 저장·화면 출력



기본 9개 분야 도구 모두 검색이 구현되어 있습니다. 모듈을 추가/제거하면 도구 목록, 선택 스키마, 화면 개수가 자동 반영됩니다.

인사 기본 정보·부서·담당자 조회와 연차 원장 기반 잔여/사용 가정 계산도 지원합니다.

답변 근거가 부족하면 질문에 관련된 부서의 실무 담당자 후보를 DB에서 찾아 사진·부서·내선·이메일·추천 이유를 카드로 표시합니다. 안내 결과는 대화 기록에 함께 저장됩니다.

연차 원장(부여·사용·예정·결재 대기)이 있으면 그 값으로 잔여 연차를 계산하고, 원장이 없으면 입사일·직급 기준 규정상 부여일수만 계산하며 잔여일수는 단정하지 않습니다. 출장비는 계산기 도구가 계산 과정·금액·관련 규정을 함께 보여줍니다([계산기 설명](docs/calculators.md)).

신청 방법 질문은 규정 표현(근태계·청구·전자결재 등)으로 추가 검색합니다. Ollama가 문장 근거 ID를 선택하여 쉬운 설명을 작성하고, 서버가 근거·기본 수치·부정 표현과 출처를 확인합니다. 확인되는 관련 내용은 먼저 제공하고, 자료에 없는 세부사항만 추가 확인을 안내합니다. 원문은 필요할 때 펼쳐볼 수 있습니다. 계산값은 Python/DB 결과를 사용합니다.



## 설정



실제 설정은 .env, 공통 로더는 app/config.py입니다. .env.example은 공유용 양식입니다.



- SQLITE_PATH: ./data/app.sqlite3

- USER_DATA_SOURCE: directory

- EMPLOYEE_DIRECTORY_DIR: ./database/employee_directory

- CHROMA_DIR: ../kdn_regulations_rag/rag_data/chroma_db (상위 폴더의 기존 규정 인덱스)

- CHROMA_COLLECTION: kdn_regulations_bge_m3_v1

- EMBEDDING_MODEL: BAAI/bge-m3

- OLLAMA_MODEL: qwen2.5:3b

- OLLAMA_ANSWER_MODEL: gemma3:4b (답변용 모델을 별도로 변경 가능)

- ENABLED_TOOLS: 빈 값이면 전체, 쉼표로 ID를 지정하면 일부만 활성화

- CONTACT_RECOMMENDATION_LIMIT: 관련 담당자 표시 수, 기본 2

- CONTACT_ROUTING_PATH: ./config/contact_topics.json, 업무별 문의 표현 연결

- FRONTEND_DIR: ./frontend_v7 (기본 화면. 이전 화면은 ./frontend에 보존)

- UI_REGULATIONS_DIR: ../WONIT_HR_UI_v7_WONIT_59_TEST/WONIT_HR_UI_v7_WONIT_59_TEST/regulations/wonit_preprocessed (화면의 규정집 PDF 원문 폴더)

- N8N_EVENT_SESSION_START / QUESTION / ANSWER / SESSION_END / FEEDBACK: n8n으로 보내는 이벤트 이름(기본 session_start, question, answer, end, feedback). 서로 달라야 합니다.

- N8N_ASYNC: 기본 true. 질문·답변 로그를 백그라운드로 보내 답변 속도에 영향을 주지 않습니다.



기존 MySQL 데이터는 유지하며 자동 이관하지 않습니다.

시작(session_start)·질문(question)·답변(answer) 단계와 종료 시점에 n8n으로 POST합니다. 종료는 만족도 없이 끝나면 end, 만족도(1~5점)와 함께 끝나면 feedback 이벤트로 나뉩니다. N8N_WEBHOOK_URL에 사용할 주소를 설정한 뒤 서버를 다시 시작하세요. 기존 .env의 URL은 유지하며 공유 양식은 빈 값입니다. 답변은 질문과 같은 message_id를 전송합니다.

주소 미설정/전송 실패에도 평가는 저장하며, 종료 화면에서 재전송할 수 있습니다.

기존 문서 인덱스는 재적재하지 않고 검색합니다.

Windows MCP 실행은 위의 `python -m app --reload` 명령을 사용하세요. 별도 MCP 서버 실행은 필요 없습니다.



## 주요 파일



| 위치 | 역할 |

| --- | --- |

| app/agent | 사용자·대화·도구 선택·답변 흐름 |

| app/mcp | 자동 등록 MCP 서버·stdio 클라이언트 |

| app/tools | 자동 등록되는 분야 도구 |

| app/rag | BGE-M3 임베딩, ChromaDB 검색 |

| app/repositories/sqlite.py | 세션별 대화·평가 저장 |

| app/repositories/users.py | 사용자 기본 정보 조회 |

| app/repositories/directory.py | 독립 사원 DB·부서·연락처·업무 역할·이미지 조회 |

| app/integrations/sqlite.py | 연결·트랜잭션·자동 스키마 초기화 |

| database/sqlite_schema.sql | SQLite 앱 DB 스키마 |

| frontend_v7 | 기본 화면(WONIT v7 UI, HTML·CSS·JS) |

| frontend | 이전 화면(보존용) |

| scripts | DB 준비·직원/연차 데이터 적재·API 명세 |

| tests | 테스트 패키지 |



## 자세한 안내



- **docs/rag-sqlite.md**: 현재 구성·도구 기능·데이터 등록·도구 추가 방법

- **docs/modules.md**: 서버/테스트/관리 모듈 실행

- **docs/configuration.md**: 공통 경로 설정

- **docs/mcp.md**: MCP 동작·독립 연결·검사

- **docs/end-webhook.md**: 단계별 n8n 이벤트·payload·만족도·실패와 재전송 범위

- **docs/implementation-notes.md**: 추가 구현 내용과 이유·남은 범위

- **docs/service-status.md**: 실제 전체 서비스 점검 결과·남은 데이터와 미구현 범위

- **docs/answer-quality.md**: 자연스러운 답변·추가 검색·관련 근거 제공 기준

- **docs/employee-directory-integration.md**: 사원 데이터·이미지 연결·화면·API·구현 이유

- **docs/contact-escalation.md**: 답변 부족 시 담당자 추천 기준·설정·검증·구현 이유

- database/employee_directory/: 별도로 만든 직원 데이터 배포 묶음

- MySQL 관련 문서는 이전 구성의 호환용 안내입니다. 현재 기본 실행에는 MySQL 서버가 필요하지 않습니다.



## 검증



```console

python -m tests -v

python -m scripts.export_openapi

```

## Ollama 모델 두 개를 동시에 메모리에 올리기

질문 분류 모델과 답변 모델이 서로 다르면, Ollama가 모델을 올리고 내리기를 반복해 질문마다 로딩 시간이 붙을 수 있습니다.
이 앱은 서버 시작 때 두 모델을 미리 올리고(WARM_UP) 계속 유지(OLLAMA_KEEP_ALIVE=-1)하지만, 동시에 몇 개까지 올릴지는 **Ollama 서버의 환경 변수**가 정합니다.

Windows(Ollama 앱): 시작 메뉴에서 "시스템 환경 변수 편집" → 환경 변수 → 사용자 변수에 `OLLAMA_MAX_LOADED_MODELS` = `2` 추가 →
작업 표시줄의 Ollama를 종료(Quit) 후 다시 실행. 그다음 챗봇 서버를 다시 시작하면 터미널에 `워밍업 완료: 모델 2개 동시 상주`가 나옵니다.
VRAM이 모자라면 두 모델이 함께 올라오지 못하므로, 그때는 `.env`의 OLLAMA_MODEL과 OLLAMA_ANSWER_MODEL을 같은 모델로 맞추세요.



- [발표 시나리오 12단계 검증·수정 기록](docs/presentation-scenario-validation.md) · [실제 질문과 답변](docs/presentation-scenario-transcript.md)
