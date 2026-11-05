# 리뷰(만족도) 저장 — n8n 이벤트 이름 맞추기

n8n `Validate and Normalize` 코드는 `session_start / question / answer / feedback / end` 다섯 이벤트만 허용합니다.
그래서 예전에 앱이 보내던 `session_end`는 `Invalid event: session_end`로 거부되어 시트에 저장되지 않았습니다.

앱은 이제 대화 종료 시 만족도 점수 유무에 따라 이벤트 이름을 나눠 보냅니다.

| 상황 | event | n8n 분기 |
|---|---|---|
| 만족도 점수(1~5) 있음 | `feedback` | Feedback - upsert |
| 점수 없이 종료 | `end` | End without feedback - upsert |

`.env`: `N8N_EVENT_SESSION_END=end`, `N8N_EVENT_FEEDBACK=feedback` (기본값과 같습니다)

## n8n 쪽 확인
- `Switch by event` 3번 출력 = `feedback`, 4번 출력 = `end` 조건인지 확인합니다.
- `Feedback - upsert` / `End without feedback - upsert` 노드의 Values to Send에서 `employee_id`, `started_at`(빈 고정값)은 **삭제**합니다.
  Code 노드가 feedback·end 이벤트에는 이 두 값을 넣지 않으므로, 남겨 두면 기존 행의 값을 빈칸으로 덮어씁니다.
- 앱은 다른 이벤트와 똑같이 n8n이 2xx로 받으면 전송 완료로 처리합니다.
