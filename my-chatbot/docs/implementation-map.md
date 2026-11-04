# 다음 세부 구현을 넣을 위치

현재 구현 상태는 **docs/rag-sqlite.md**가 기준입니다. SQLite·기존 ChromaDB 검색·Ollama 단일 도구 선택과 모든 분야 검색이 구현되었습니다.
이 문서의 MySQL 관련 연결 지점은 이전 구성의 호환용입니다.

현재 UI·API·도구 호출 흐름을 유지하면서 아래 경계에 구현을 추가합니다.

| 구현할 내용 | 시작할 파일 | 연결할 곳 |
| --- | --- | --- |
| 분야별 규정 검색·조회·계산 | app/tools/<분야 ID>.py | execute(ToolInput) → ToolResult |
| Ollama 도구 선택 | app/integrations/ollama.py | app/agent/router.py의 select_tools 대체 |
| 도구별 arguments 추출·검증 | app/agent/service.py | 선택 → 인자 검증 → 실행, 부족하면 되묻기 |
| 답변용 컨텍스트 | app/agent/context.py | 질문·대화·도구 결과·출처 |
| Ollama 최종 답변 (연결 완료) | app/integrations/ollama.py | ANSWER_PROVIDER=ollama로 활성화 |
| PDF 읽기·조항 분할 | app/rag/loader.py | scripts/ingest.py |
| 임베딩 | app/rag/embeddings.py | 적재·검색에서 동일 모델 사용 |
| ChromaDB 저장·검색 | app/rag/vector_store.py | settings.chroma_dir / chroma_collection |
| RAG 통합 검색 | app/rag/pipeline.py | 각 분야 도구에서 domain 지정 후 호출 |
| MySQL 연결 (구현 완료) | app/integrations/mysql.py | .env의 MYSQL_* 사용 |
| MySQL 대화·평가 저장 (구현 완료) | app/repositories/mysql.py | STORAGE_BACKEND=mysql로 선택 |
| 대화 종료 n8n 전송 | app/integrations/n8n.py | service.py의 end()에서 호출 |
| 프론트 화면 | frontend/index.html, css/styles.css | JS는 js/chat.js / 통신은 js/api.js |

## 도구 계약

공통 입력: `question`, `employee_id`, `conversation_id`, `arguments`.
현재 arguments는 빈 객체입니다. 각 업무의 날짜·일수·기준일 등은 구현 단계에서 별도 모델로 검증합니다.
공통 출력: `tool_id`, `status`, `message`, `data`, `sources`.

- `ok`: 실제 조회·계산 완료
- `no_result`: 관련 근거 없음
- `needs_input`: 필수 정보가 부족하여 되묻기 필요
- `not_implemented`: 아직 구현하지 않음 (현재 상태)
- `error`: 실행 오류

실제 LLM 도구 스키마에는 등록 도구 이름과 업무별 입력 모델을 제공하도록 확장합니다.
현재 분야 목록은 도구 호출 스키마 자체가 아닙니다.

## 종료 이벤트

`conversation.ended` 이벤트의 payload는 대화 ID·event_id·사번·종료 시각·평가·의견·메시지 목록입니다.
MySQL 모드에서는 종료 상태·평가·webhook_events를 한 트랜잭션으로 영구 저장합니다.
실제 외부 전송은 하지 않습니다. 향후 별도 전송 작업에서 n8n으로 전달합니다.
n8n은 event_id 기준으로 중복을 방지하도록 구현합니다.
전송 실패가 채팅 답변이나 대화 종료를 막지 않도록 하며, 실패 이벤트는 재시도합니다.
저장 시 대화 행 잠금과 마지막 메시지 ID 검증으로 동시 질문/종료와 오래된 컨텍스트 저장을 방지합니다.

## 다음 단계 검증 기준

- RAG는 존재하는 문서·페이지를 반환하고, 관련도 기준 미달은 근거 없음으로 처리합니다.
- 휴가 계산은 가상 데이터와 규칙을 먼저 확정하고 날짜·반차·중복·음수·초과를 검증합니다.
- Ollama는 모델 설정·응답 형식·도구 인자·반복 호출 횟수·타임아웃을 검증합니다.
- MySQL은 메모리 저장소와 같은 동작, 재시작 후 복원, 종료 중복 요청을 검증합니다.
- n8n은 수신 성공·지연·실패·중복 요청을 검증합니다.
