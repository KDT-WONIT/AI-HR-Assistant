# API 인터페이스

FastAPI의 Pydantic 모델이 계약의 기준입니다. 실행 후 `/docs`, `/openapi.json`에서 확인합니다.
기본 저장소는 `STORAGE_BACKEND=sqlite`, 답변 제공자는 `ANSWER_PROVIDER=ollama`입니다.
규정 검색·직원 조회·연차 원장 기반 계산이 구현되었습니다. 실제 n8n 전송은 구현 전입니다.
현재 구성의 상세 계약은 docs/rag-sqlite.md를 참고하세요.

| 메서드 | 경로 | 역할 |
| --- | --- | --- |
| GET | `/api/health` | 모드와 연결 구현 상태 |
| GET | `/api/tools` | 현재 등록된 분야 도구 목록 |
| GET | `/api/users/{employee_id}` | 사용자 ID로 기본 정보 사전 조회 |
| POST | `/api/conversations` | 사번으로 새 대화 생성 |
| GET | `/api/conversations/{id}` | 대화 및 메시지 조회 |
| POST | `/api/chat` | 질문 → 도구 선택 → 검색/조회 → 컨텍스트 → 근거 검증 답변 |
| POST | `/api/conversations/{id}/end` | 대화 종료·선택 평가·n8n 이벤트 준비 |

## 질문

```json
{
  "conversation_id": "대화 생성 응답의 UUID",
  "employee_id": "TEST-001",
  "message": "연차 신청 방법을 알려주세요",
  "tool_id": null
}
```

`conversation_id` 생략 시 새 대화를 만듭니다. `tool_id` 생략 시
현재 등록된 분야 중 하나를 Ollama로 선택합니다. 지정하면 해당 도구 하나를 직접 호출합니다.
응답은 `conversation_id`, `message_id`, `answer`, `status`, `sources`, `tools_used`,
`tool_results`, `context`, `steps`, `mode`, `answer_provider`를 포함합니다. `message_id`는 답변 메시지의 ID입니다.
도구는 `ok`, `no_result`, `needs_input`으로 처리 결과를 명시합니다. 답변 상태는 `answered`, `no_result`, `needs_input`입니다.
출처·계산값을 만들어내지 않습니다.
현재 세션의 최근 메시지 5~10개(기본 10개)를 DB에서 조회해 `context.history`에 시간순으로 넣습니다.
같은 ID의 최신 사용자 정보를 별도로 조회해 `context.user_profile`에 넣습니다.
`context.user_profile_status`는 `found` 또는 `not_found`이며, 미등록 ID는 null 프로필로 처리합니다.
프로필 소스는 USER_DATA_SOURCE로 SQLite/이전 MySQL 직원 뷰 또는 JSON 파일을 선택합니다.
현재 질문은 별도로 추가합니다. 질문/답변 저장이 완료된 후 응답합니다.
Ollama가 고른 문장이 실제 원문에 있는지 검증하고 원문 조각과 출처를 출력합니다.

## 종료

```json
{"rating": "helpful", "comment": "찾기 쉬웠습니다"}
```

`rating`은 `helpful` / `neutral` / `unhelpful` / null, `comment`는 최대 1000자입니다.
종료 응답에는 대화 ID, 종료 시각, 평가, `event_id`, `webhook_status`가 포함됩니다.
같은 대화를 다시 종료하면 최초 종료 응답을 반환하며 평가·이벤트를 중복 생성하지 않습니다.
현재 웹훅 상태는 URL이 없으면 `not_configured`, 있으면 `not_implemented`입니다.
대화 종료 자체는 성공하지만 **외부로는 전송하지 않습니다**. SQLite 모드는 종료·평가·이벤트를
한 트랜잭션으로 저장합니다. 메모리 모드에서만 서버 재시작 시 기록이 사라집니다.

## 오류

- `404`: 없는 대화
- `409`: 종료된 대화에 질문 / 대화 사번 불일치 / 동시 요청으로 이전 기록이 바뀜
- `422`: 빈 질문·잘못된 ID·등록되지 않은 도구·허용 길이 초과
- `501`: `APP_MODE=live`인데 ANSWER_PROVIDER가 demo
- `502`: Ollama 호출 실패·빈 응답·타임아웃
- `503`: SQLite 조회/저장 또는 임베딩/ChromaDB 검색 실패 (다른 저장소로 자동 전환하지 않음)

`GET /api/health`의 `storage`, `storage_status`, `answer_provider`, `history_message_limit`,
`chat_available`로 실행 상태를 확인합니다. MySQL 연결 실패 시 `status=degraded`입니다.

사번은 가상 직원 식별값이며 인증 수단이 아닙니다. 현재 로컬 데모용 계약입니다.
