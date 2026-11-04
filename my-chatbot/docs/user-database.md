# 사용자 정보 DB

프로젝트 자료의 **가상 직원 100명**을 기존 MySQL `ai_hr_assistant`에 적재합니다.
사번은 모든 사용자 테이블과 대화 기록에서 동일한 직원 한 명을 가리킵니다.

## 테이블 구성

| 테이블 | 저장 내용 | 연결 |
| --- | --- | --- |
| employees | 사번, 이름, 직급, 입사일, 고용형태, 재직상태 | employee_id 기본키 |
| departments | 부서명, 상위 부서, 기능, 위치, 대표 내선 | parent_dept_id → departments |
| employee_assignments | 소속 부서, 직책, 시작·종료일, 주 소속 여부 | employee_id → employees, dept_id → departments |
| duty_roles | 부서장·실무담당자 등 업무 역할 정의 | role_id 기본키 |
| employee_roles | 직원별 업무 역할과 유효기간 | employee_id → employees, role_id → duty_roles |
| employee_contacts | 이메일, 내선, 근무지, 연락처 공개범위, 사진 정보 | employee_id → employees, 직원당 한 행 |

`v_employee_profiles`는 직원별 현재 주 소속과 연락처를 한 행으로 조회하는 뷰입니다.
현재 소속은 한국 날짜 기준이며 시작일·종료일을 모두 포함합니다.
복수의 유효 주 소속이 잘못 등록되면 시작일과 소속 ID의 내림차순으로 한 건을 선택합니다.
CSV 적재 단계에서는 주 소속 기간 중복을 거절합니다. 이후 직접 SQL로 수정할 때도 기간 중복을 확인하세요.

기존 `employees.name`, `hired_at`은 유지합니다. CSV의 `employee_name`은 `name`으로,
`hire_date`는 `hired_at`으로 변환합니다. 기존 `department`, `job_title`은 이전 JSON 가져오기와의
호환용이며 새 직원 CSV의 소속·직책은 `employee_assignments`에 저장합니다.
뷰는 유효한 주 소속이 있으면 이를 우선하고, 없으면 이전 기본 필드를 사용합니다.
기존 MySQL 사용자 조회도 이 뷰를 사용하므로 사번 조회와 대화 컨텍스트에 현재 부서가 반영됩니다.

기존 `conversations.employee_id`에는 미등록 테스트 사번으로 만든 기록도 있으므로 강제 외래키를 추가하지 않았습니다.
`employee_queries.sql`처럼 사번으로 연결해 이름·대화·평가를 함께 조회합니다.
업무 역할은 담당 업무 구분이며 로그인 권한은 아닙니다. 현재 사번 입력은 인증 기능이 아닙니다.

## 실행

프로젝트 `my-chatbot` 폴더에서 실행합니다. 기존 `.env`의 MySQL 접속정보와 비밀번호가 필요합니다.
비밀번호를 SQL이나 실행 파일에 적지 않습니다.

```powershell
# 1. DB에 접속하지 않고 자료와 사진 매핑만 검증
.\.venv\Scripts\python.exe -m scripts.seed_employees --check-only

# 2. 테이블 생성 및 기존 프로젝트 DB의 컬럼 확장
.\.venv\Scripts\python.exe -m scripts.init_db

# 3. 검증한 가상 사용자 자료 추가
.\.venv\Scripts\python.exe -m scripts.seed_employees
```

대상 자료의 정상 행 수는 부서 16, 업무 역할 5, 직원 100, 소속 이력 100, 역할 배정 100, 연락처 100입니다.
초기화는 기존 기록을 삭제하지 않습니다. MySQL의 테이블 변경은 자동 커밋되므로 전체 초기화가 하나의 롤백 단위는 아닙니다.
직원 자료 적재는 전체를 한 트랜잭션으로 처리해 오류 시 이번에 추가한 행을 모두 롤백합니다.
외래키 검사를 끄거나 `INSERT IGNORE`로 오류를 숨기지 않습니다.

재실행 시 **기본키가 이미 있는 행은 그대로 유지**합니다. CSV를 수정해 다시 실행해도 기존 행을 덮어쓰지 않습니다.
이메일 중복 등 다른 제약 위반이 있으면 전체 적재가 실패합니다. 기존 사번과 샘플 사번이 겹치면 기존 데이터와의 일치 여부를 먼저 확인하세요.
직원 사진 검수 결과나 사용자 수정값을 재적재로 되돌리지 않도록 한 동작입니다.

기본 자료 위치는 프로젝트 옆 `data/KDN_Enterprise_AI_Dataset/KDN_Enterprise_AI_Dataset_Pexels`입니다.
다른 PC에서는 `.env`의 `EMPLOYEE_DATASET_DIR`로 변경하거나 실행 시 `--dataset-dir "D:/자료폴더"`를 지정합니다.
상대 경로인 설정값은 `my-chatbot` 기준이며 명령행 인자는 실행 위치 기준입니다.
이 경로는 `DATA_DIR`와 독립적입니다.

원본 데이터셋의 `sql/01_create_schema.sql`, `02_seed_data.sql`은 43개 테이블의 별도 DB용입니다.
이 앱의 테이블과 컬럼이 다르므로 앱 DB에는 위 실행 파일을 사용하세요.
이미 원본 `enterprise_ai_agent` DB를 구축한 경우 이 초기화 스크립트로 같은 DB를 덮어 구성하지 마세요.

## 사진 저장

사진은 DB에 바이너리로 넣지 않고 원본 자료의 경로와 URL을 저장합니다.

| 컬럼 | 의미 |
| --- | --- |
| photo_path | 자료 폴더 기준 JPG 상대 경로. 현재 파일은 없음 |
| photo_url | Pexels 원본 후보 이미지 주소 |
| photo_status | 원본 CSV의 검수 상태. 현재 REVIEW_PENDING |
| photo_source / photo_alt | 출처 구분과 가상 직원임을 설명하는 대체 문구 |
| source_page_url / license_url | 원본 출처 페이지·라이선스 주소 |
| fallback_photo_path | 실제 포함된 assets/profiles/사번.svg 기본 아이콘 |
| photo_file_status | 적재 시 로컬 파일 존재 여부. PRESENT 또는 NOT_DOWNLOADED |

직원 CSV와 사진 출처 명세의 사번 목록이 일치하는지 검증합니다.
현재 100장의 JPG는 다운로드되지 않았고 100개 SVG 아이콘은 존재합니다.
검수 상태는 자동 승인하지 않으며 이 작업에서 외부 사진을 다운로드하거나 UI에 노출하지 않습니다.
향후 화면 연결 시 검수 전 사진은 기본 아이콘을 표시하고, 승인·파일 준비가 끝난 뒤 사진을 표시하면 됩니다.
경로는 브라우저 URL이 아니므로 정적 파일 제공 경로는 화면 구현 시 별도로 연결해야 합니다.
`photo_file_status`는 적재 시점의 값이므로 이후 파일을 다운로드하면 상태를 별도로 갱신합니다.

## 조회

```sql
SELECT * FROM v_employee_profiles WHERE employee_id = 'KDN0001';
```

`database/employee_queries.sql`에는 사번 조회, 부서별 직원, 업무 역할, 소속 이력, 대화·평가 연결,
사진 진행 상태 조회가 있습니다. 앱에서 사용하는 실제 사번은 문자열을 조합하지 않고 `%s` 인자로 전달합니다.

## 검증

기본 테스트는 CSV 중복, 없는 부모 참조, 부서 순환, 주 소속 기간 중복, 사진 경로 이탈을 확인합니다.
MySQL 통합 테스트는 `RUN_MYSQL_TESTS=1`과 이름이 `_test`로 끝나는 전용 DB에서만 실행합니다.
테이블을 먼저 초기화한 뒤 `python -m tests -v`를 실행합니다.
직원 100명 조회, 기존 사용자 조회 연동, 재적재 시 중복 방지, 외래키 및 이메일 충돌 롤백을 검사합니다.

2026-11-04 검증 결과: 기본 테스트 26개 통과, 별도 MySQL 8.4.11에서 직원·기존 대화 저장 통합 테스트 8개 통과.
기존 employees 테이블에서의 확장과 반복 초기화, 실제 MySQL을 사용하는 사번 조회 API·채팅 컨텍스트도 확인했습니다.
Ollama HTTP 통합 테스트 3개는 이번 DB 작업의 검증 대상에서 제외했습니다.
현재 프로젝트 `.env`의 MySQL 비밀번호가 비어 있어 사용자 로컬 기본 DB에는 적용하지 않았습니다.
