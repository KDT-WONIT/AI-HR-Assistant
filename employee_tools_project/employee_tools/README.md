# 사원 규정 안내 Tool 5종

Python 3.11 이상. 수업 예제의 함수·타입 힌트·docstring·JSON Tool 정의·Registry 방식으로 작성했습니다.

## 기능 파일

| 파일 | 공개 함수 | 기능 |
|---|---|---|
| rag_search_tool.py | search_regulations | 제공된 Chroma 규정 검색, 출처·실제 PDF 페이지 반환 |
| leave_status_tool.py | get_leave_status | 로그인 사원의 부여·사용·예약·잔여량과 추가 계획 계산 |
| contact_lookup_tool.py | get_responsible_contact | 답변 불가 주제의 등록 담당자·전화·이메일 조회 |
| travel_expense_tool.py | calculate_travel_expense | 국내·국외 일반 출장 예상액 계산 |
| inquiry_history_tool.py | search_inquiry_history | 로그인 사원 본인의 문의 이력 검색 |

각 파일의 `TOOL_DEFINITION`은 LLM에 전달하는 JSON Schema입니다. `common.py`, `database.py`, `tool_registry.py`는 이 다섯 파일이 공유하는 코드입니다. 패키지 폴더 전체를 같은 위치에 유지하세요.

## 현재 연결 상태

- 규정 DB: 프로젝트의 `data/rag_data`에 포함된 Chroma 컬렉션 `kdn_regulations_bge_m3_v1`, dataset `kdn-regulations`, 59개 PDF·7,117개 청크를 확인했습니다.
- 임베딩: 저장된 `BAAI/bge-m3`, 1024차원, 정규화 설정, 개정본 `5617a9f61b028005a4858fdac845db406aefb181`을 사용합니다. 다른 임베딩 모델로 대체하지 않습니다.
- 사원 DB: SQLite 어댑터는 구현했지만 실제 팀원 DB와 테이블 구조는 아직 제공되지 않았습니다. `sql_queries.json`을 실제 구조에 맞게 매핑해야 합니다. 실제 사원·휴가·담당자 정보를 가짜 데이터로 대신하지 않습니다.
- 여비: 제공된 여비규정 개정번호 38, 시행일 2025-08-04의 표·조항을 코드로 옮겼습니다. 규정이 변경되면 요율과 예외 처리를 함께 재검토해야 합니다.

## 프로젝트 폴더와 최초 준비

ZIP을 풀면 나오는 `employee_tools_project` 전체가 하나의 프로젝트입니다.

```text
employee_tools_project/
  README.md
  employee_tools/               # Python Tool과 연결 파일
  data/
    employee/employee.sqlite3   # 나중에 팀원의 실제 DB를 넣는 자리
    rag_data/                  # 제공된 규정 데이터와 Vector DB 포함
  models/bge-m3/               # 최초 한 번 내부에 다운로드
  .runtime/                    # 프로젝트 내부 캐시
```

파일 위치는 프로그램의 위치를 기준으로 찾습니다. `EMPLOYEE_DB_PATH`, `RAG_DATA_DIR`, `EMPLOYEE_SQL_PATH`를 설정할 필요가 없고, 기존 PC의 이 값도 사용하지 않습니다. 다른 폴더에서 프로그램을 호출해도 같은 프로젝트의 파일을 읽습니다. 별도 경로를 코드에서 지정할 때도 프로젝트 내부 경로만 허용합니다.

Python 3.11 이상이 설치된 환경에서 프로젝트 최상위 폴더를 열고 최초 한 번 준비합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r employee_tools/requirements-mcp.txt --cache-dir .runtime/pip-cache
.\.venv\Scripts\python.exe -m employee_tools.prepare_model
```

가상환경과 패키지도 `.venv` 내부에 설치합니다. 모델은 처음 한 번 인터넷으로 받아 `models/bge-m3`에 저장하고 이후에는 내부 모델만 읽습니다. 모델 캐시도 `.runtime`에 저장합니다. 이 ZIP에는 규정 데이터가 실제 포함되어 있으며 모델 가중치는 최초 준비 시 내려받습니다.

Windows Chroma 1.5.9의 색인 경로 제약으로 **프로젝트 폴더 전체 경로는 영문을 사용**하세요. 특정 PC의 Downloads 폴더 등으로 데이터를 따로 빼둘 필요는 없습니다.

사원번호는 파일 경로가 아니라 접속할 때 받는 값입니다. `EmployeeTools(employee_id=...)` 또는 `--employee-id`로 서버에서 전달합니다.

## 팀원 SQLite DB 연결

`schema.example.sql`은 연동 규약을 설명하는 예시이며 실제 DB 구조를 추정한 파일이 아닙니다. 기존 DB를 이 예시로 다시 만들 필요가 없습니다. 조회문에서 `실제컬럼 AS 기대컬럼`으로 매핑하면 됩니다.

`employee_tools/sql_queries.json`의 다섯 조회문을 실제 DB 구조에 맞게 수정합니다. SQL은 서버 설정이며 LLM이 생성하는 인자에 포함하지 않습니다. 값은 SQLite 바인딩 매개변수로 전달하고 DB는 읽기 전용으로 엽니다.

| 조회문 | 필수 반환 컬럼 |
|---|---|
| employee | employee_id, name, department, job_title, travel_grade |
| leave_balance | employee_id, leave_type, period_start, period_end, granted_days, carried_days, adjustment_days, expired_days |
| leave_usage | usage_id, employee_id, leave_type, used_on, days, status |
| contacts | contact_id, name, department, topic, keywords_json, phone, email |
| inquiries | inquiry_id, employee_id, question, answer, category, created_at, status |

날짜는 YYYY-MM-DD, 문의 시각은 정렬 가능한 ISO 형식으로 반환하세요. 사원번호는 앞의 0을 보존하는 문자열입니다. 사원·휴가·이력 SQL에는 반드시 `:employee_id` 조건을 유지하세요. 반환 행의 사원번호도 재검사합니다.

여비용 `travel_grade`는 `executive`, `grade_1`, `grade_2`, `grade_3`, `grade_4_plus` 중 하나입니다. 실제 직급 코드와 다르면 SELECT의 CASE 표현식 등으로 매핑하세요. AI가 직급이나 조회 사원번호를 바꾸는 인자는 없습니다.

휴가 규약:

- 부여기간은 DB의 실제 기간을 사용하며 1월~12월로 가정하지 않습니다. 규정에 있는 입사일 기준 기간을 반영할 수 있습니다.
- 부여일수·이월·조정·소멸은 DB가 제공하는 유효한 집계값입니다. 입사일만으로 부여일수를 추측하지 않습니다. 과거 기준일을 지원하려면 SQL도 그 기준일의 부여·이월·소멸 상태를 반환해야 합니다.
- usage는 휴무·공휴일과 근무 형태를 반영한 **날짜별 실제 차감 일수**입니다. 전일 1, 반일 0.5, 반반일 0.25 등을 매핑하세요. 기간 총량을 날짜마다 복제하면 안 됩니다.
- approved: 승인, pending: 대기, cancelled: 취소, rejected: 반려로 매핑합니다.
- `unused_days = 부여+이월+조정-소멸-기준일까지 승인 사용량`.
- `remaining_days = unused_days-미래 승인 예약량`. 대기·취소·반려는 차감하지 않습니다.
- `planned_days`는 미등록 사용 계획의 계산일 뿐 DB에 신청하거나 저장하지 않습니다.

담당자는 활성 디렉터리만 사용합니다. `keywords_json`은 `["연차", "이월"]`처럼 구성합니다. 주제가 일치하지 않으면 DB에 `topic='general'`로 명시된 일반 담당자만 대체로 제공합니다. 규정 제·개정 이력의 결재자를 현재 담당자로 해석하지 않습니다.

## 일반 Python/Agent 연결

```python
from employee_tools.database import SqliteRepository
from employee_tools.tool_registry import EmployeeTools

# employee_id는 접속 시 서버에 보관한 사원번호로 전달합니다.
tools = EmployeeTools(employee_id='000123', repository=SqliteRepository())
llm_tools = tools.definitions
result = tools.execute_tool({
    'tool_name': 'get_leave_status',
    'arguments': {'planned_days': 0.5},
})
```

사원번호 입력 화면 자체는 구현 범위에 포함하지 않았습니다. 기존 접속 흐름에서 받은 번호가 DB에 있는지 확인하여 문맥을 만들며, 이 확인이 비밀번호나 SSO 인증을 대신하는 것은 아닙니다. 사원별 요청마다 별도 `EmployeeTools`를 사용하세요.

RAG만 단독으로 확인하려면 사원 DB 없이도 호출할 수 있습니다.

```python
from employee_tools.rag_search_tool import RegulationSearch
rag = RegulationSearch()  # 같은 프로젝트의 data/rag_data를 자동 사용
result = rag.search_regulations('연차휴가 이월 기준은 무엇인가요?', top_k=5)
```

`max_distance` 기본값은 없음입니다. 실제 질문·정답으로 검증한 후 임계값을 지정하세요. 거리는 정답 확률이 아니므로 검색 성공만으로 답변 가능하다고 판정하지 않습니다. Agent는 근거 부족이나 `needs_review`를 받으면 `get_responsible_contact`를 호출하도록 연결하세요.

## 국내 출장 입력 예

```json
{
  "tool_name": "calculate_travel_expense",
  "arguments": {
    "trip": {
      "trip_type": "domestic",
      "start_date": "2026-11-04",
      "end_date": "2026-11-05",
      "destination_city": "서울",
      "distance_km": 600,
      "same_city": false,
      "domestic_region_type": "special_city",
      "transport_cost_krw": 50000
    }
  }
}
```

`distance_km`는 편도 거리가 아닌 전체 출장거리입니다. 숙박 지역 구분은 `special_city`(특별시), `metropolitan_city`(광역시), `special_autonomous`(특별자치시·도), `other`(그 외)입니다.

일반 직원 2일 출장에서는 일비 50,000원 + 식비 60,000원 + 서울 숙박 한도 예산 100,000원 + 입력 교통비 50,000원 = 260,000원입니다. 숙박 단가를 입력하면 한도 내 예상 지출액을 사용합니다. 임원·1직급은 국내 숙박비가 실비라서 예상 숙박 단가가 없으면 총액을 확정하지 않습니다.

50km 미만 또는 동일 시·군인 경우 근거리 규정을 확인합니다. 단일 일자 대중교통·자가차량 근거가 명확한 경우 10km 미만 20,000원, 10~25km 미만 30,000원, 25~50km 미만 40,000원이며 교통비·일비·식비를 중복 합산하지 않습니다. 1일 장거리 무숙박 출장은 식비 2/3를 적용합니다.

## 국외 출장 입력 예

```json
{
  "tool_name": "calculate_travel_expense",
  "arguments": {
    "trip": {
      "trip_type": "overseas",
      "start_date": "2026-11-04",
      "end_date": "2026-11-05",
      "destination_country": "일본",
      "destination_city": "도쿄",
      "lodging_nights": 1,
      "meal_days": 2,
      "transport_cost_krw": 600000,
      "exchange_rate_krw_per_usd": 1400,
      "approval_date": "2026-10-30",
      "exchange_rate_date": "2026-10-30",
      "exchange_rate_basis": "hana_cash_buy_opening"
    }
  }
}
```

위 환율·교통비는 **사용법 설명용 가상 입력**입니다. 실제 시세가 아닙니다. 국외 `meal_days`, `lodging_nights`는 기내·선박 체류 및 무료 제공분을 제외한 지급 대상 수량을 명시하세요. 국외 숙박 예상 단가는 USD, 교통비·통행료는 KRW입니다. 환율은 규정상 품의일 하나은행 현찰 살 때 시초가를 별도로 확인하여 입력합니다. 자동 시세 조회나 현재 환율 추측은 하지 않습니다.

도쿄 등 규정에 열거된 도시는 가등급, 그 외는 나등급이며 스위스는 모든 도시가 가등급입니다. 숙박 예상 단가가 없으면 해당 USD 한도를 예산으로 사용합니다. 표시 소수점 반올림은 예상액 표시용이며 정산 절사 규정의 구현이 아닙니다.

## 여비 적용 범위와 담당자 전환

- 국내 단일 지역 일반 출장, 국외 28일 이내 일반 출장의 정액·숙박 한도 예산을 지원합니다.
- 렌터카 일비 50%, 국내 연속 장기 출장의 도착 다음 날부터 30일 전액·다음 30일 90%·이후 80%, 승인된 숙박 초과 한도 국내 30%·국외 50%를 반영합니다.
- 요금 등급에 맞는 교통비 예상액은 입력값입니다. 항공권·연료비·통행료를 외부에서 조회하거나 증빙을 심사하는 Tool은 아닙니다.
- 교통비·실비 숙박액·환율이 미정이면 `partial`, `missing_inputs`, `estimated_total_krw=null`로 반환합니다.
- 회사차량의 근거리 지급은 본문 제20조제5항과 별표3 주석의 적용관계가 명확하지 않아 `needs_review`로 반환합니다. 일반 회사 제공 차량의 일비 제외 범위도 담당자 확인으로 전환합니다.
- 국외 1개월 초과 일비 80%의 적용기간 해석을 확정하지 않아 28일 초과는 `needs_review`로 돌립니다. 29~31일도 보수적으로 확인 대상에 포함됩니다.
- 임원 동행·IR 특례·기관 비용 부담·부분 식사 제공·복수 도시·7일 이내 분할 재출장·마일리지 가산·신분 변경 등은 `special_conditions`에 명시하면 담당자 확인으로 전환합니다.
- 가족여비·전근여비·파견 특례·취소수수료·사망 여비는 계산하지 않습니다. 숙박 초과 실비 특례도 일반 추가 한도를 넘는 경우 담당자 확인이 필요합니다.

`policy_basis.json`에는 계산 요율과 연결되는 실제 청크 ID·PDF 페이지·근거 원문을 기록했습니다. PDF 페이지는 인쇄 페이지와 다를 수 있습니다.

## MCP와 n8n 연결

```powershell
.\.venv\Scripts\python.exe -m employee_tools.mcp_server --employee-id 000123
```

MCP는 수업 예제와 같은 **stdio** 방식이고 한 서버 프로세스는 한 로그인 사원에 고정됩니다. 하나의 공용 프로세스에서 접속 사원을 여러 사용자 요청 사이에 바꾸면 안 됩니다. 원격·다중 사용자 n8n 서비스에서는 세션 문맥을 서버에서 바인딩하는 HTTP 연결을 별도로 구성해야 합니다. 이 패키지에 공개 HTTP 서버는 포함하지 않았습니다.

서버에서 Python 실행이 가능한 자체 호스팅 환경 등에서는 JSON을 표준입력으로 넘겨 1회 실행할 수도 있습니다. 사용자 입력을 셸 명령 문자열로 붙이지 말고 프로세스 API의 입력 스트림을 사용하세요.

```powershell
'{"tool_name":"search_inquiry_history","arguments":{"query":"휴가"}}' | .\.venv\Scripts\python.exe -X utf8 -m employee_tools.run_tool --employee-id 000123
```

n8n 또는 Agent는 `success` / `partial` / `not_found` / `needs_review` / `error`를 분기할 수 있습니다. 팀원 DB가 없는 상태에서는 SQLite 관련 Tool이 설정 오류를 반환하는 것이 정상입니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pip install -r employee_tools/requirements-dev.txt --cache-dir .runtime/pip-cache
.\.venv\Scripts\python.exe -m pytest employee_tools/tests -q
```

임시 SQLite 테스트 데이터로 휴가 계산, 사원 간 이력 분리, SQL 값 바인딩, 담당자 미등록 처리, 국내·국외 요율과 경계값, 미입력 금액, 임의 사원·직급 변경 차단을 검증합니다. 테스트 사원·담당자는 테스트 코드에만 있습니다. 실제 사용자 DB 연결, BGE-M3 자연어 검색 품질, n8n 운영 연결은 별도 확인 대상입니다.

도메인 계산에 더해 폴더 이동·외부 경로 차단·내부 모델 다운로드 흐름을 테스트합니다. 압축을 푼 프로젝트 내부 DB를 열어 7,117개 청크 수·실제 저장 벡터 재조회·출처·페이지 반환을 확인했습니다. 이 검증은 자연어 질문을 BGE-M3로 새로 임베딩한 의미 검색 품질 검증과 구분됩니다. `VALIDATION.md`를 참고하세요.
