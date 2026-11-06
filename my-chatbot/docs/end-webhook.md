# 채팅 단계별 n8n POST

프론트는 FastAPI에 요청하고, FastAPI가 `.env`의 `N8N_WEBHOOK_URL`로 JSON POST합니다.
PowerShell 예시의 **session_start / question** 이벤트와 필드명을 그대로 사용합니다.
브라우저에 외부 웹훅 주소를 노출하지 않으며 Google Sheets 처리 코드는 추가하지 않았습니다.
기존 `.env`의 URL은 유지했습니다. 현재 n8n 화면의 Test URL을 직접 확인하거나 외부 테스트 행을 추가하지 않았습니다.

## 전송 시점

| 사용자 동작 / 처리 | event 기본값 | 주요 필드 |
| --- | --- | --- |
| 첫 질문 시 새 세션 생성 | session_start | session_id, employee_id, started_at, session_status=OPEN, user |
| 질문 입력·전송 후 모델 처리 전 | question | session_id, message_id, employee_id, question, asked_at, answer_status=PENDING |
| 답변 생성·로컬 DB 저장 후 | answer | 동일한 message_id, question, answer, answer_message_id, answer_status=ANSWERED, processing_status, category, tools_used, answered_at |
| 대화 종료 창에서 만족도 제출 | session_end | session_id, employee_id, session_status=CLOSED, rating, comment, user, started_at, ended_at, 최근 messages |

새 대화 버튼은 입력 상태를 초기화합니다. 사번이 정해지고 첫 질문을 보낼 때 실제 세션이 만들어집니다.
직접 `POST /api/chat`으로 새 세션을 만들 때도 session_start → question → answer 순으로 전송합니다.
화면 복원·기록 조회·만족도 팝업 열기·취소에는 POST 이벤트를 만들지 않습니다.

모든 이벤트에 event_id(UUID), session_id(대화 UUID), employee_id, conversation_id(호환용), occurred_at(UTC ISO-8601)을 포함합니다.
Content-Type은 `application/json; charset=utf-8`, Idempotency-Key는 event_id입니다.
한국어·이모지는 JSON UTF-8로 전송합니다.

## PowerShell 예시와 같은 질문 형식

```json
{
  "event": "question",
  "event_id": "이벤트 UUID",
  "session_id": "대화 UUID",
  "conversation_id": "대화 UUID",
  "message_id": "질문 메시지 UUID",
  "employee_id": "WON0001",
  "question": "연차를 신청하려면 어떻게 해야 하나요?",
  "answer_status": "PENDING",
  "asked_at": "2026-11-04T04:00:00+00:00",
  "occurred_at": "2026-11-04T04:00:00+00:00"
}
```

answer 이벤트의 message_id는 위 질문 ID와 같습니다. 앱 내부 답변 ID는 별도 answer_message_id로 보냅니다.
따라서 n8n에서 같은 qa_log 행을 연결할 수 있습니다. 답변이 생성되어 반환되면 answer_status는 ANSWERED이며,
근거 부족·추가 정보 필요 같은 업무 처리 상태는 processing_status(answered / needs_review / no_result / needs_input)에 들어갑니다.
모델·도구·저장 오류 시에는 같은 질문 ID로 answer_status=FAILED, answer="", error_code=chat_processing_failed를 보낸 뒤 기존 API 오류를 반환합니다.
실패한 질문·답변 쌍을 로컬 대화 기록에 반쪽 저장하지 않는 동작은 유지합니다.

## 만족도와 사용자 정보

session_end는 종료와 만족도를 한 이벤트로 보냅니다. rating은 helpful / neutral / unhelpful / null이며 comment는 의견입니다.
사용자 기본 정보 user는 employee_id, name, department, job_title만 포함합니다. 미등록자는 employee_id만 보냅니다.
질문·답변 단계에는 전체 해당 텍스트를 보냅니다. 종료 이벤트에는 최근 최대 10개 메시지, 메시지당 1,000자만 보내며 설정으로 조정합니다.
전체 RAG 컨텍스트·규정 원문 조각·임베딩·담당자 카드 메타데이터는 별도로 전송하지 않습니다.

## 설정

```dotenv
N8N_WEBHOOK_URL=
N8N_TIMEOUT_SECONDS=10
N8N_EVENT_SESSION_START=session_start
N8N_EVENT_QUESTION=question
N8N_EVENT_ANSWER=answer
N8N_EVENT_SESSION_END=end
N8N_EVENT_FEEDBACK=feedback
N8N_MESSAGE_LIMIT=10
N8N_MESSAGE_MAX_CHARS=1000
```

URL은 전체 주소를 지정하고 서버를 재시작합니다. 공유용 `.env.example`의 주소는 빈 값입니다.
사용자가 제공한 코드에 없는 답변·만족도 이벤트 이름은 answer / session_end를 기본으로 정했습니다.
n8n Switch가 다른 이름을 쓰면 위 설정값만 바꾸면 됩니다. 이전 종료 형식은 N8N_EVENT_SESSION_END=conversation.ended로 선택할 수 있습니다.
이미 저장된 종료 이벤트의 재전송은 당시 저장된 event 이름과 payload를 그대로 사용합니다.

n8n의 Test URL은 Listen for Test Event / Execute workflow로 등록되는 테스트용이며,
연속 서비스에는 게시된 워크플로의 Production URL을 사용합니다.
참고: [n8n 공식 Webhook 문서](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/).

## 전송 실패와 재시도 범위

- URL이 비어 있으면 외부 요청을 생략합니다.
- 단계별 요청은 순서대로 실행하며 각 요청의 대기 시간 상한은 N8N_TIMEOUT_SECONDS입니다.
- 2xx는 sent, HTTP 오류·연결 오류·타임아웃·JSON 응답 ok:false는 failed입니다. HTTP 성공만으로 시트 적재까지 검증한 것은 아닙니다.
- 시작·질문·답변 전송은 한 번씩 시도합니다. 실패해도 채팅은 계속하며 API의 webhook_events와 화면 안내·서버 경고 로그에 결과를 남깁니다. 해당 이벤트의 영속 전송 대기열·자동 재시도는 포함하지 않았습니다.
- 종료·만족도는 기존처럼 평가와 payload를 로컬 DB에 먼저 저장하고 전송합니다. 실패 시 화면의 n8n 다시 전송 또는 POST /api/conversations/{id}/webhook/retry를 사용합니다. 같은 event_id로 재전송하며 이미 sent이면 중복 전송하지 않습니다.
- 네트워크 타임아웃·프로세스 강제 종료 시 상대편 수신 여부가 불확실할 수 있습니다. 발신 앱만으로 시트 기록의 exactly-once를 보장하지 않습니다.

## 추가 구현과 검증

질문을 모델 처리 전에 전송하여 PENDING 기록을 만들고, 실제 답변과 같은 message_id로 연결했습니다.
생성 실패 이벤트는 n8n에 PENDING만 남는 상황을 줄이기 위해 추가했습니다.
전송 실패 시 채팅을 막지 않는 처리·실패 안내는 외부 기록 서버 장애 중에도 로컬 대화를 유지하기 위한 것입니다.
이벤트 이름 설정은 별도 n8n 작업의 Switch 이름에 맞추기 위해 추가했습니다.

2026-11-04 로컬 임시 HTTP 수신기를 사용한 통합 검사 및 API·설정·담당자 회귀 검사 **42개 통과**.
시작→질문→답변→만족도 순서, 동일 질문 ID, 한국어, 로컬 저장, 생성 실패, HTTP 오류, 타임아웃, ok:false,
URL 미설정, 이벤트 이름 변경, 종료 재전송·중복 방지를 검사했습니다. 외부 n8n과 Google Sheets는 변경하지 않았습니다.

```console
python -m unittest tests.test_api tests.test_webhook tests.test_config tests.test_contact_escalation -q
```

테스트 패키지는 실제 .env URL로 실수로 전송하지 않도록 외부 URL을 비웁니다. 통합 검사는 임시 로컬 수신기 주소를 명시적으로 사용합니다.

## 구글 시트 열 이름과 맞춘 필드

기존 필드는 그대로 두고, 시트 열과 같은 이름의 필드를 함께 보냅니다. 값이 없으면 빈 문자열(만족도 점수는 null)입니다.

| 시트 | 이벤트 | 시트 열 ← 필드 |
| --- | --- | --- |
| 세션 | session_start / session_end | session_id, employee_id, started_at, ended_at, session_status(OPEN/CLOSED), satisfaction_score, satisfaction_comment |
| 질문·답변 | question / answer | session_id, employee_id, question_at, question, answer_at, answer, answer_status, answer_source, handler_id, handler_name, handler_department, handler_contact |

- satisfaction_score: helpful=5, neutral=3, unhelpful=1, 미선택은 null. satisfaction_comment는 의견입니다.
- answer_status: PENDING(질문 접수) → ANSWERED / ESCALATED(근거 부족으로 담당자 안내) / FAILED(처리 실패).
- answer_source: RAG(규정 근거) / TOOL(업무 조회) / HR_ROUTING(담당자 안내) / NORMAL(검색·도구 없이 답한 일반 대화) / PENDING(질문 접수) / ERROR(처리 실패). 담당자 열(handler_*)은 담당자가 없으면 "-"로 기록해 빈칸을 만들지 않습니다.
- handler_*: 추천된 첫 번째 담당자의 사번·이름·부서·연락처(이메일, 없으면 내선). 없으면 빈 값.
- 질문·답변 행은 message_id로 이어 붙이고 question 이벤트의 PENDING 행을 answer 이벤트로 갱신합니다.

## 백그라운드 전송 (N8N_ASYNC)

기본값(N8N_ASYNC=true)에서는 session_start / question / answer 로그를 백그라운드로 보내고 답변은 기다리지 않습니다.
API 응답의 webhook_events 상태는 `queued`이며, 실제 전송 실패는 서버 로그의 경고로 확인합니다.
같은 대화의 이벤트는 보낸 순서대로 전송되고, 대화 종료(session_end) 전에는 대기 중인 로그를 먼저 보냅니다.
서버를 끌 때도 남은 로그를 마저 보냅니다(최대 N8N_TIMEOUT_SECONDS+5초). 전송 결과를 바로 확인하려면 N8N_ASYNC=false로 두세요.

