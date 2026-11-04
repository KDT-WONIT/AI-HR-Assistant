# 설정과 경로를 관리하는 곳

**실제 값은 `.env`, 코드에서 사용하는 설정은 `app/config.py` 한곳에서 관리합니다.**
공유용 기본 양식은 `.env.example`입니다. 값이 중복되는 별도의 컨텍스트 파일은 만들지 않습니다.
비밀번호·웹훅 URL을 포함한 `.env` 및 `.env.*` 파일은 Git에서 제외하며 `.env.example`만 공유합니다.

## 적용 규칙

1. 실행 환경변수가 `.env`보다 우선합니다. `.env`에 없으면 코드의 기본값을 사용합니다.
2. `.env`는 실행 위치와 관계없이 `my-chatbot/.env`에서 읽습니다.
3. 상대 경로는 항상 **my-chatbot 프로젝트 폴더 기준**입니다. 절대 경로도 사용할 수 있습니다.
4. 하위 경로가 비어 있으면 상위 경로를 따라 자동 계산합니다.
5. 값을 바꾸면 서버를 재시작합니다. 폴더 생성·파일 이동·DB 접속은 설정을 읽는 것만으로 실행하지 않습니다.

예를 들어 `DATA_DIR=D:/hr-project/data`로 바꾸면, 별도 지정하지 않은 PDF·CSV·ChromaDB·모델 캐시
경로가 모두 해당 폴더 아래로 이동합니다. 기존 파일은 직접 옮겨야 합니다.

## 관리 항목

| 설정 | 기본값 / 용도 |
| --- | --- |
| MYSQL_HOST / MYSQL_PORT | 127.0.0.1 / 3306 |
| MYSQL_DATABASE / MYSQL_USER / MYSQL_PASSWORD | MySQL DB·계정·비밀번호 |
| STORAGE_BACKEND | sqlite (기본), memory / mysql은 테스트·이전 호환용 |
| USER_DATA_SOURCE=directory | 독립 사원 DB를 현재 사용자 정보 원본으로 사용 |
| EMPLOYEE_DIRECTORY_DIR | 기본 ./database/employee_directory, 사원 DB 묶음·로컬 이미지 경로 |
| EMPLOYEE_DIRECTORY_DB | 선택 설정. DB 파일 경로를 별도 지정하며 기본값은 위 폴더의 employee_directory.sqlite3 |
| SQLITE_PATH | DATA_DIR/app.sqlite3. 대화/평가/연차 원장 SQLite |
| SQLITE_SCHEMA_PATH | ./database/sqlite_schema.sql |
| TOOL_ROUTER | ollama (기본) 또는 manual |
| ENABLED_TOOLS | 비우면 전체, 도구 ID를 쉼표로 지정하면 일부만 사용 |
| ANSWER_PROVIDER | demo 또는 ollama |
| HISTORY_MESSAGE_LIMIT | 최근 메시지 수, 5~10, 기본 10 |
| CONTACT_RECOMMENDATION_LIMIT | 답변 부족 시 관련 업무 담당자 후보 수, 1~5, 기본 2 |
| CONTACT_ROUTING_PATH | ./config/contact_topics.json, 질문 표현과 부서 업무 연결 규칙 |
| USER_DATA_SOURCE | directory / auto / sqlite / mysql / file. 현재 directory로 독립 사원 DB 조회 |
| USER_DATA_PATH | DATA_DIR/raw/users.json. JSON 프로필 파일 |
| OLLAMA_BASE_URL / OLLAMA_MODEL | Ollama 서버·설치 모델 |
| OLLAMA_ANSWER_MODEL | 최종 답변용 모델, 기본 gemma3:4b. OLLAMA_MODEL은 도구 선택용 |
| OLLAMA_TIMEOUT_SECONDS | 답변 대기 시간, 기본 60초 |
| MCP_TIMEOUT_SECONDS | 로컬 MCP 도구 호출 제한, 기본 180초 |
| N8N_WEBHOOK_URL | n8n 웹훅 전체 주소. 기본 빈 값이면 외부 POST 없음 |
| N8N_TIMEOUT_SECONDS | 웹훅 POST 제한, 기본 10초 |
| N8N_MESSAGE_LIMIT / N8N_MESSAGE_MAX_CHARS | 전송할 최근 메시지 수(기본 10)·각 메시지 길이(기본 1000) |
| N8N_EVENT_SESSION_START / N8N_EVENT_QUESTION | 시작·질문 이벤트 이름, 기본 session_start / question |
| N8N_EVENT_ANSWER / N8N_EVENT_SESSION_END | 답변·만족도 종료 이벤트 이름, 기본 answer / session_end |
| VECTOR_BACKEND | chroma |
| DATA_DIR | ./data |
| POLICY_DIR | DATA_DIR/raw/policies |
| CSV_DIR | DATA_DIR/raw/csv |
| EMPLOYEE_DATASET_DIR | 프로젝트 옆 data/KDN_Enterprise_AI_Dataset/KDN_Enterprise_AI_Dataset_Pexels |
| PROCESSED_DIR | DATA_DIR/processed |
| CHUNKS_DIR | PROCESSED_DIR/chunks |
| VECTOR_DIR | DATA_DIR/vector_store |
| CHROMA_DIR | ./chroma_db. 제공된 기존 규정 DB |
| CHROMA_COLLECTION | kdn_regulations_bge_m3_v1 |
| EMBEDDING_MODEL | BAAI/bge-m3 |
| EMBEDDING_REVISION | 기존 인덱스와 같은 5617a9f61b028005a4858fdac845db406aefb181 |
| EMBEDDING_DEVICE | cpu |
| RAG_TOP_K | 5 |
| RAG_MAX_DISTANCE | 0.60. cosine 거리 상한 |
| EMBEDDING_CACHE_DIR | DATA_DIR/models |
| FRONTEND_DIR | ./frontend |
| PROMPTS_DIR | ./prompts |
| LOGS_DIR | ./logs |
| DATABASE_SCHEMA_PATH | ./database/schema.sql |

MySQL의 실제 데이터 파일 폴더는 MySQL 서버가 관리합니다. 앱에서는 접속정보만 설정합니다.
직원과 대화는 각각 독립된 SQLite DB를 사용합니다. 규정 벡터 DB는 제공된 ChromaDB를 사용하며 실제 검색이 구현되었습니다.
CHROMA_DIR는 기존 인덱스가 있는 별도 경로라 DATA_DIR 변경을 따라 이동하지 않습니다.
EMBEDDING_CACHE_DIR에 실제 BGE-M3 모델을 캐시합니다. LOGS_DIR은 진단 로그용 공통 경로입니다.

## 현재 적용 경로 확인

```powershell
.\.venv\Scripts\python.exe -m scripts.show_paths
```

비밀번호나 웹훅 URL을 출력하지 않고 정규화된 경로만 보여줍니다.

## 코드에서 사용

```python
from app.config import settings

pdf_directory = settings.policy_path("work_labor")
chroma_directory = settings.chroma_dir
chroma_collection = settings.chroma_collection
```

새 구현에서는 `.env`를 따로 읽거나 경로를 하드코딩하지 말고 `settings`를 사용하세요.
프론트 폴더, 9개 분야의 자료 폴더, Ollama 시스템 프롬프트, MySQL 초기 SQL 파일,
ChromaDB 인터페이스의 저장 위치와 컬렉션 이름이 이 설정에 연결되어 있습니다.
