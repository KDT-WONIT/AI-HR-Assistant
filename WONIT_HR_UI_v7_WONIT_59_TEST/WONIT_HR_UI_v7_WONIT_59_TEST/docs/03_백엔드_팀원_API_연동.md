# v7 → 실제 백엔드·n8n·AI Agent 팀 연동 명세

## 프론트엔드 업무 범위

- `employee_id`, `question`, `category_id`(선택), `session_id`, `previous_request_id`, `input_data`를 서버로 전송합니다.
- 직원 조회 성공·실패, 질문 답변, 계산 결과, 출처, 담당자, 추가 질문, 이력, 만족도를 사용자에게 표시합니다.
- PDF 분류/문서 목록 UI와 PDF 열람, 132개 질문 예시를 구현합니다.
- AI 도구를 프론트에서 호출하지 않고 결과를 수신해 렌더링합니다.

## 팀에서 확정한 Tool 5개

| Tool 구분 | 역할 | 프론트 UI 대응 |
|---|---|---|
| `rag_regulation_search` | PDF 규정 검색·근거 반환 | 항목별 답변·출처·원문 열기 |
| `leave_status_and_calculation` | 개인 휴가 현황 조회 + 기간/잔여량 계산 통합 | 휴가 입력 폼·계산 내역 카드 |
| `hr_contact_lookup` | 문의 분야별 담당자 조회 | 담당자 카드·사진·전화·메일 |
| `travel_expense_calculation` | 출장 일정·여비 계산 | 출장비 입력 폼·예상 항목별 계산 |
| `inquiry_history_search` | 문의 기록/채팅방 검색 | 채팅방 목록·전체 대화 상세·검색 |

**직원 조회는 사번 확인 API 단계이며 Tool 목록에 넣지 않습니다.**

질문에 맞는 도구를 결정하는 **LLM 기반 tool selection은 백엔드 AI Agent/MCP 영역**입니다. 프론트는 토글로 선택한 `category_id`를 **선택적 분류 힌트**로 전송하며, 선택하지 않은 경우 백엔드가 자동 분류합니다.

## 현재 모의 API 경로

- `POST /api/hr/employee` 직원 조회 (가상 DB)
- `POST /api/hr/question` 일반 챗봇 답변
- `POST /api/hr/question/stream` SSE 실시간 시뮬레이션
- `POST /api/hr/history` 직원별 채팅방 목록
- `POST /api/hr/conversation` 채팅방 전체 메시지
- `POST /api/hr/contact` 담당자
- `POST /api/hr/feedback` 문의 만족도 저장
- `GET /api/health` 서버 상태

### 질문 요청 JSON 예시

```json
{
  "employee_id":"W-1001",
  "session_id":"session-a",
  "previous_request_id":"T-ABC12345",
  "category_id":"work_leave_labor",
  "question":"3일 사용하면 얼마나 남나요?"
}
```

### 답변 JSON 필수 구조

```json
{
  "request_id":"Q-0001",
  "session_id":"session-a",
  "employee_id":"W-1001",
  "status":"answered",
  "answer":"(서버에서 검증해 생성한 실제 답변)",
  "sources":[],
  "sections":[],
  "calculation":null,
  "contact":null,
  "follow_up":null
}
```

복합 질문 `needs_review`, 정보 부족 `needs_info`, 처리 불가 `error`는 백엔드가 결정합니다. `sources`에는 실제 문서 제목·문서ID·페이지·조항·URL을 포함해야 합니다.

**SSE**인 경우 `event: delta`에 `{ "text": "..." }`, 마지막 `event: final`에 위 JSON 전체를 보냅니다.

## 규정 문서 목록 연동

- 현재는 `assets/regulations_catalog.json`에서 **실제 업로드된 PDF 59개**를 읽고 `regulations/wonit_preprocessed/`에서 원문을 정적으로 제공합니다.
- 운영 서버에서는 인가된 사용자에게 문서 목록·검색·파일/페이지 열람 API 제공이 필요합니다.
- PDF 전처리 교체 후 RAG 색인도 함께 다시 생성해야 합니다. 파일명만 변경해도 RAG의 실제 답변 내용이 바뀌지 않습니다.

## 채팅방 이력 필수 계약

- `POST /api/hr/history` → `conversations` 배열로 채팅방 목록 반환; 각 항목에 `session_id`, `title`, `updated_at`, `turn_count`.
- `POST /api/hr/conversation` + `session_id` → 전체 `turns` 배열; 각 turn에 `question`, `answer`, `created_at`, `request_id` 등.
- `session_id`는 같은 채팅방 동안 유지; 신규 대화에서 새 ID 생성.
- n8n/Google Sheets에 질문 행을 저장할 수는 있지만 **채팅방 조회 API에서는 session_id 기준으로 묶어서 반환**해야 합니다.

## 실제 운영 보안 유의사항

사번만으로는 본인인증이 되지 않습니다. 실제 직원 데이터를 연결하면 서버 측 SSO/로그인 인증, 직원별 접근 권한 확인, 문서 권한, 호출 제한, 개인정보 보호가 필요합니다. 모의 서버를 공인 인터넷에 직접 노출하지 마세요.
