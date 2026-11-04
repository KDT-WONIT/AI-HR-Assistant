# 저장/대화 컨텍스트 검증

## 사원 디렉터리 연동 검사

2026-11-04, `tests.test_directory_integration`, `tests.test_config`, `tests.test_sqlite_rag.SQLiteTests`의 20개 검사가 통과했습니다.
사원 프로필·연락처·역할·부서 인원·검색·이미지 경로·읽기 전용·연차 원장 사번 참조를 확인했습니다.
실제 실행 중인 서비스의 사용자/검색/부서/이미지 API와 MCP의 개인 정보·부서 대표 내선 답변도 별도로 확인했습니다.
자세한 데이터 연결·추가 구현 이유는 employee-directory-integration.md를 참고하세요.

## 현재 SQLite/RAG 구성 검증

현재 구성은 docs/rag-sqlite.md를 참고하세요. 2026-11-04 답변 개선 중 전체 84개 검사에서 76개 통과·이전 MySQL 전용 8개 제외를 확인했습니다.
이후 긍정 조건/국내·해외 적용 범위 검사 2개를 추가했고, 최신 답변·검색 품질 검사 15개는 모두 통과했습니다.
최신 전체 86개 재검사에서는 Windows의 socket.socketpair 생성/로컬 연결 중 WinError 10014가 발생했습니다.
서비스와 같은 Python 3.13으로도 재현되어 전체 최신 검사는 통과로 기록하지 않습니다. 실패 로그는 logs/test-answer-quality*.txt에 있습니다.
실제 실행 중인 웹 서비스에서 연차 신청·학자금 질문의 MCP 검색과 최종 답변 생성은 별도로 확인했습니다.
임시 SQLite의 원자적 저장·최근 대화·프로필/연차 계산, 문서 필터·거리·출처, 도구 자동 등록/개수 변경,
원문에 없는 답변 문장 거절, 로컬 모의 Ollama의 JSON 선택·HTTP 오류·타임아웃을 확인했습니다.
별도로 실제 제공된 ChromaDB의 59개 문서가 모두 분야에 매핑되고 9개 도구가 각 분야 근거를 반환함을 확인했습니다.
실제 설치된 Ollama + BGE-M3 + SQLite로 단일 도구 선택·답변·근거 없음·기록 복원을 확인했습니다.
브라우저에서도 질문 → 자동 분야 선택 → 검색 근거 5개 → Ollama 답변 → SQLite 저장을 확인했습니다.
후속 질문에는 이전 메시지 2개와 사용자 정보가 포함됐습니다. 현재 답변 검증은 문장 근거 ID 방식이며, 원문 전체 표시 대신 읽기 쉬운 확인 한계 안내를 검사합니다.
신청 질문의 추가 검색, 공통 근태계 제출 조항 우선순위, 실제 문장 근거 연결, 관련 정보 부분 제공,
다른 휴가의 제출 기한 오적용 방지, 문서의 다음 조항을 잘못 출처로 표시하지 않는지를 추가 검증했습니다.
MCP SDK의 실제 stdio 연결·목록·구조화 호출, 도구 12개 자동 등록, 잘못된 인자/프로필 주입 거절,
통신 오류/타임아웃의 반쪽 저장 방지, Windows Selector→Proactor 통신 루프를 검사했습니다.
로컬 HTTP 수신기에 가상 데이터만 전송하여 n8n POST 계약·2xx·503·타임아웃·빈 URL·재전송·동시 종료 중복 방지를 확인했습니다.
외부 n8n URL과 실제 워크시트 저장은 검증하지 않았습니다.
최종 브라우저 검사에서는 실제 stdio MCP의 급여/복리후생 도구 → 규정 5개 → Ollama 답변 → SQLite 저장 후,
만족도 helpful 제출과 종료 이벤트 not_configured 저장(전송 시도 0회)을 확인했습니다.
아래 MySQL 검증 내역은 이전 구성의 기록입니다.

## 기본 API 테스트

```powershell
$env:STORAGE_BACKEND='memory'
$env:ANSWER_PROVIDER='demo'
.\.venv\Scripts\python.exe -m tests -v
```

## MySQL + Ollama HTTP 모의 서버

운영 DB를 사용하지 마세요. 이름이 `_test`로 끝나는 전용 DB를 지정합니다.
테스트는 랜덤 대화를 생성하고 기존 기록을 삭제하지 않습니다.

터미널 1:

```powershell
postman simulation run postman/simulations/ollama-history.sim.yaml --port 14501 --no-history --output ndjson
```

터미널 2 (계정과 비밀번호는 로컬 테스트 계정으로 설정):

```powershell
$env:STORAGE_BACKEND='mysql'
$env:MYSQL_DATABASE='ai_hr_assistant_test'
$env:MYSQL_HOST='127.0.0.1'
$env:MYSQL_PORT='3306'
$env:MYSQL_USER='테스트_계정'
$env:MYSQL_PASSWORD='테스트_비밀번호'
$env:ANSWER_PROVIDER='demo'
$env:HISTORY_MESSAGE_LIMIT='10'
$env:RUN_MYSQL_TESTS='1'
$env:RUN_OLLAMA_TESTS='1'
$env:OLLAMA_BASE_URL='http://127.0.0.1:14501/ollama'
.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe -m tests -v
```

## 이번 검증 결과

2026-11-04, MySQL 8.4.11의 분리된 임시 인스턴스와 Postman CLI 1.75.0의 로컬 모의 서버에서
15개 테스트가 통과했습니다.

- FastAPI 경로를 통한 질문/답변의 MySQL 저장
- 같은 사번의 다른 세션과 기록 분리
- 전체 이력 유지, 최근 5개/10개만 시간순 조회
- 새 DB 연결에서 대화/종료 평가 복원
- 질문과 답변의 원자적 저장, 중간 오류 시 롤백
- 종료 중복 요청 방지, 종료 후 질문 거절, 오래된 컨텍스트 저장 거절
- Ollama 실제 HTTP 요청에 system + 이전 10개 + 현재 질문 한 번 전달
- 모의 HTTP 500·잘못된 응답·타임아웃을 오류로 처리
- 모델 실패 시 반쪽 대화 기록 없음

시뮬레이션 로그에서 POST /api/chat 호출과 200/500 응답을 확인했습니다.
실제 Ollama 모델 추론이나 사용자 로컬 DB 계정에 대한 연결 성공을 의미하지는 않습니다.
모의 응답은 공식 Ollama Chat API 형태를 따르며 모델의 답변 품질은 검사하지 않습니다.

## 사용자 프로필 확장 검증

답변 부족 시 관련 업무 담당자 안내의 최신 44개 테스트 및 실제 서비스 검증은 [contact-escalation.md](contact-escalation.md)를 참고하세요.

2026-11-04, 사용자 ID 기반 프로필 결합 추가 후 전체 37개 테스트가 통과했습니다.
MySQL 8.4.11의 임시 DB에서 프로필 등록/갱신·직원 뷰 조회·대화 컨텍스트 저장을 확인했습니다.
현재 ID의 프로필과 최근 10개 메시지가 Ollama HTTP 요청에 함께 들어가는 것도 확인했습니다.
중복 사용자 ID·잘못된 파일·미등록 ID·프로필 변경 후 재조회·다른 사용자 정보 제외를 검증했습니다.
실제 모델 추론은 포함하지 않습니다.

이번에는 실행 도구의 환경 오류를 피해 같은 모의 핸들러를 Node로 직접 실행했습니다.
직접 실행할 경우 `/ollama` 경로 접두어 없이 주소를 설정합니다.

```powershell
# 터미널 1
$env:PORT='14501'
node postman/mocks/ollama/default.js

# 터미널 2: MySQL 테스트 설정은 위와 동일
$env:OLLAMA_BASE_URL='http://127.0.0.1:14501'
$env:USER_DATA_SOURCE='auto'
$env:RUN_OLLAMA_TESTS='1'
.\.venv\Scripts\python.exe -m tests -v
```
