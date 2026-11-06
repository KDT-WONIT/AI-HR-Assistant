# WONIT v7 UI와 기존 서비스 연결

적용일: 2026-11-05.

제공받은 `WONIT_HR_UI_v7_WONIT_59_TEST/WONIT_HR_UI_v7_WONIT_59_TEST` 화면을
`frontend_v7`에 복사해 실제 서비스에 연결했습니다. 기존 `frontend`는 보존했습니다. 규정집 PDF 59개는 `data/regulations_pdf`로 옮겨 이 프로젝트 폴더 안에서 모두 제공되며, 전달받은 원본 폴더는 더 이상 필요하지 않아 삭제했습니다.
모의 서버 `mock_server.py`와 5510 포트는 사용하지 않습니다.

## 실행과 설정

```console
python -m app --reload
```

화면: http://127.0.0.1:8000/ . 이미 열려 있던 화면은 새로고침하세요.

```dotenv
FRONTEND_DIR=./frontend_v7
UI_REGULATIONS_DIR=./data/regulations_pdf
OLLAMA_THINK=false
```

DB·ChromaDB·Ollama 모델명·n8n URL은 기존 `.env` 설정을 유지합니다.
프론트 config.js는 같은 서버의 API 주소만 포함하며 n8n URL은 브라우저에 넣지 않습니다.
기존 프론트로 돌아가려면 FRONTEND_DIR=./frontend로 설정하고 재시작할 수 있습니다.

## 연결한 기능

| 새 화면 | 연결 내용 |
| --- | --- |
| 사번 확인·사용자 표시 | 현재 사원 DB의 이름·부서·직급·내선·이메일 |
| 사원·부서 찾기 | 이름/사번/부서 검색·부서 필터·더 보기·현재 사번 선택·프로필 사진 |
| AI 질문 분야 | 서버의 MCP 도구 목록을 자동 반영. 규정집 분류 10개와 실제 업무 도구 분류를 분리 |
| 채팅 | 기존 Agent → MCP → ChromaDB/업무 조회 → Ollama → SQLite 저장. 일반 대화 기능 유지 |
| 실시간 출력 | 기존 status / 누적 delta / final을 새 UI의 상태·교체 미리보기·최종 답변으로 변환 |
| 답변·근거 | 기존 핵심 내용 보강·표 복원·강조 유지. 출처·페이지·검색 원문·색인 원본 PDF 링크 |
| 담당자 | 답변 부족 시 추천 카드 및 분야별 담당자 조회. 사진·부서·내선·메일·추천 이유 |
| 처리 정보 | 답변 아래 펼치기에서 처리 과정·시간·도구 결과·컨텍스트 확인 |
| 문의 이력 | 현재 사번의 채팅방 목록·내용 검색·전체 대화 복원·종료 상태 복원 |
| 새로고침 | 현재 탭의 세션 ID와 사번을 sessionStorage에 보관하여 서버 DB에서 복원 |
| 휴가 입력폼 | 기간과 실제 사용 예정 일수를 전달하여 기존 잔여/부여 기준 계산 호출 |
| 출장 입력폼 | 국내/국외·도시·일정·거리·동일 시군·교통비·숙박·식비 입력을 기존 출장 Tool에 전달 |
| 종료·별점 | 1~5점 원값·오류 유형·의견을 저장하고 종료. 종료된 채팅은 읽기만 가능 |
| n8n | 기존 단계별 POST 유지. 종료 전송 실패 시 같은 이벤트 재전송 버튼 연결 |
| 규정집 | 제공된 59개 PDF 목록·분야별 탐색·검색·새 창·다운로드 |

규정집의 제공 PDF와 검색 출처의 색인 원본은 경로를 구분합니다.
답변의 원문 링크는 ChromaDB 데이터 묶음의 summary.json에 등록된 document_id와 원본 파일을 대조합니다.
임의 파일 경로를 받지 않습니다. 브라우저에 내장 PDF 뷰어가 없으면 미리보기 대신 새 창/다운로드를 사용합니다.

## 연결을 위해 추가한 부분과 이유

- `app/api/ui.py`: 새 화면의 `/api/hr/...` 계약을 기존 API·서비스에 연결하기 위해 추가했습니다.
  기존 `/api/chat`, `/api/chat/stream`, `/api/users` 등의 경로는 유지합니다.
- 실제 서버에서 만든 세션 ID를 사용합니다. 새 UI의 임시 UUID를 DB 세션으로 오인하지 않도록 첫 질문 전에 생성합니다.
- 별점 1~5점 원값과 오류 유형은 기존 end_result JSON 및 n8n payload에 추가합니다.
  기존 helpful/neutral/unhelpful은 호환용으로 유지하며 4~5/3/1~2점에 대응합니다.
- 답변 상태는 기존 context_data에 함께 저장하여 복원할 때 담당자 카드가 있다는 이유만으로 상태를 바꾸지 않습니다.
- 입력폼에서 명시한 값은 검증된 ToolArguments로 전달합니다. LLM이 입력 일수·거리·비용을 다시 추측하지 않도록 했습니다.
- 휴일·개인 근무표 DB가 없으므로 날짜만으로 실제 휴가 차감량을 확정하지 않습니다. 실제 사용 예정 일수 입력을 추가했습니다.
- 문의 목록·상세·평가·재전송은 사번과 세션 소유자를 대조합니다. 기존처럼 사번은 테스트 식별값이며 로그인 인증은 별개입니다.
- 원본 프론트 파일을 보존하고 새 작업용 폴더를 만들었습니다. 전달받은 파일에 변경 내용이 섞이지 않도록 했습니다.

## API 계약

| 경로 | 용도 |
| --- | --- |
| POST /api/hr/employee | 사번 프로필 확인 |
| POST /api/hr/question | 비스트리밍 질문 |
| POST /api/hr/question/stream | 상태·교체 미리보기·최종 응답 SSE |
| POST /api/hr/history | 현재 사번의 채팅방 검색 |
| POST /api/hr/conversation | 현재 사번 소유 세션의 전체 대화 |
| POST /api/hr/contact | 관련 담당자 조회 |
| POST /api/hr/feedback | 별점·오류·의견 저장 및 종료 |
| POST /api/hr/retry | 종료 n8n 이벤트 재전송 |
| GET /api/hr/source/{document_id} | 검색 원본 PDF 열람 |

질문 필드: employee_id, session_id, question, 선택 category_id/previous_request_id/input_data.
응답 필드: request_id, session_id, employee_id, status, answer, sources, contact, steps, context, tool_results, webhook_events.
실제 도구 개수는 서버에서 조회합니다. 새 UI의 기존 분류 ID는 호환 매핑으로 연결했습니다.

## 간헐적인 Ollama 오류 보완

사용자가 본 일반 오류만으로 당시 원인을 확정할 수는 없습니다.
진단 시 서버 연결·설치 모델·메모리 상주는 정상이며, 현재 모델은 gemma4:e2b였습니다.
실제 도구 선택 응답에서 본문과 별도의 thinking 출력을 확인했습니다.
동일 연봉 질문의 관찰값: 기존 624 출력 토큰(내부 추론 포함), think=false 적용 후 25 출력 토큰·추론 0자·정상 도구 선택.
이는 해당 점검의 관찰값이며 모든 질문의 성능 보장은 아닙니다.

구조화된 도구 선택·답변에서 본문에 출력 예산을 쓰도록 OLLAMA_THINK=false를 추가했습니다.
빈 본문에만 1회 자동 재시도하고, 계속 비어 있으면 오류를 반환합니다.
연결 실패·시간 초과·모델 HTTP 오류·빈 본문·추론 한도 소진·응답 형식을 구분하고 처리 단계를 표시합니다.
원인이 다른 연결/메모리/시간 초과 문제를 이 변경으로 해결했다고 단정하지 않습니다.
공식 요청 규격: [Ollama API의 think 옵션](https://github.com/ollama/ollama/blob/main/docs/openapi.yaml).

## 검증

2026-11-05 다음 **52개 테스트 통과**:

```console
python -m unittest tests.test_ui_v7 tests.test_ollama_response_errors tests.test_config -q
python -m unittest tests.test_api tests.test_webhook -q
```

새 UI·모델 오류·설정 25개, 기존 API·n8n 회귀 27개입니다.
JS 문법 검사와 API 명세 생성도 완료했습니다.

별도 8010 서버에서 실제 사원 DB·MCP·ChromaDB·Gemma4로 연봉 질문을 실행했습니다.
답변·출처·담당자 표시, 사원/부서 검색, 4점 평가와 종료, 새로고침 복원,
채팅방 목록·복원 및 규정집 목록·PDF 연결을 브라우저에서 확인했습니다.
테스트는 별도 logs/ui-v7-qa.sqlite3와 빈 n8n URL을 사용하여 기존 대화 DB와 외부 워크시트에 테스트 행을 추가하지 않았습니다.
이 테스트 서버는 점검 후 종료하며 실제 서비스는 기존 8000 포트를 사용합니다.

결과 이미지: screenshots/wonit-v7-connected.png.

최종 읽기 점검에서 기존 8000 서비스의 WONIT v7 화면·새 API·health=ok를 확인했습니다. 규정집 PDF와 검색 원본 PDF는 모두 HTTP 200, application/pdf 및 PDF 헤더를 확인했습니다. 브라우저에서 제출한 별점 4점과 closed 상태도 별도 DB에서 확인했습니다.
