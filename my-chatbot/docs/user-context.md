# 사용자 ID 기반 컨텍스트

사용자 기본 정보와 대화 기록을 분리해서 관리합니다.
현재 `employee_id`를 사용자 ID로 사용합니다. 사용 전 화면의 사번 입력란에 이 ID를 입력하세요.
ID는 가상 사용자 식별값이며 로그인/인증 기능은 별도입니다.

## 처리 흐름

1. 입력한 사용자 ID로 대화를 만듭니다. 세션 도중 ID는 바뀌지 않습니다.
2. 질문마다 해당 ID의 최신 기본 정보를 조회합니다.
3. 도구 입력에도 기본 정보를 전달합니다. 도구의 세부 구현에서 활용할 수 있습니다.
4. 기본 정보 + 최근 대화 5~10개 + 현재 질문 + 도구 결과/규정 출처를 컨텍스트로 만듭니다.
5. Ollama에는 현재 사용자의 프로필만 전달합니다.
6. MySQL 모드에서는 답변에 사용한 프로필이 `messages.context_data`에도 함께 기록됩니다.

기본 필드는 `employee_id`, `name`, `department`, `job_title`, `hired_at`입니다.
연차 잔여량 등 업무 데이터는 앞으로 해당 Tool에서 조회하도록 확장합니다.
사용자 프로필만으로 휴가/수당 자격이나 회사 규정을 임의로 계산하지 않습니다.
정보가 없으면 `user_profile=null`, `user_profile_status=not_found`로 표시합니다.
없는 프로필을 다른 사용자 데이터로 대체하지 않습니다. 조회 실패는 `503`으로 알립니다.

## 방법 A: MySQL 사용자 테이블

```dotenv
USER_DATA_SOURCE=mysql
```

`.env`의 MYSQL_* 접속정보를 사용하고 `employees`와 현재 부서/직무를 결합한
`v_employee_profiles` 뷰에서 해당 ID의 기본 필드 한 건만 조회합니다.
기본 스키마는 이미 `database/schema.sql`에 있습니다.
`scripts/init_db.py`를 다시 실행하면 기존 직원 기록을 유지하며 뷰도 준비됩니다.
원본 직원 100명과 사진 정보 적재는 `docs/user-database.md`를 참고하세요.

사용자 데이터는 JSON으로 준비한 뒤 한 번에 등록하거나 갱신할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe -m scripts.import_users --file data/raw/users.json
```

같은 ID는 이름·부서·직급·입사일을 갱신하고 기존 대화 기록은 유지합니다.
소속 이력을 등록한 직원의 부서·직책은 유효한 주 소속이 우선하므로 변경 시 `employee_assignments`도 갱신하세요.
파일에 없는 사용자를 삭제하지 않습니다. JSON은 완전한 프로필 목록이며 생략된 선택 필드는 null로 갱신됩니다.
등록 작업이 실패하면 해당 파일의 변경을 롤백합니다.

## 방법 B: JSON으로 별도 관리

```dotenv
USER_DATA_SOURCE=file
USER_DATA_PATH=./data/raw/users.json
```

JSON 파일을 수정하면 다음 질문부터 적용됩니다. MySQL에 대화를 저장하면서 프로필만 JSON으로 관리할 수도 있습니다.
`users.example.json`은 가상 사용자 2명의 예시이며 현재 `users.json`에도 복사해 두었습니다.
TEST-001, TEST-002로 흐름을 확인하고 실제 사용할 가상 데이터로 교체하세요.

```json
[
  {
    "employee_id": "TEST-001",
    "name": "테스트 사용자",
    "department": "개발팀",
    "job_title": "사원",
    "hired_at": "2025-01-02"
  }
]
```

파일의 중복 ID, 잘못된 날짜, 정의되지 않은 필드는 오류로 처리합니다.
실제 사용자 데이터 파일은 Git에서 제외하고 예시 파일만 공유합니다.

기본값 `USER_DATA_SOURCE=auto`는 sqlite이면 SQLite의 직원 프로필 뷰, mysql이면 MySQL, memory이면 파일을 사용합니다.
현재 기본 설정은 SQLite이며 자세한 구성은 docs/rag-sqlite.md를 참고하세요.
`USER_DATA_PATH`를 비워두면 `DATA_DIR/raw/users.json`을 사용합니다.
데이터 소스나 경로 설정을 변경한 경우 서버를 재시작하세요.

## 사전 조회 API

`GET /api/users/TEST-001`

응답의 `status=found`이면 `profile`에 기본 정보가 있습니다. 미등록 ID는 `not_found`와 null을 반환합니다.
이 API로 채팅 시작 전 사용자 확인 화면을 붙일 수 있습니다.
채팅 API가 받는 ID 필드명도 `employee_id`이며 세션의 ID와 일치해야 합니다.

## 구현 위치

- `app/repositories/users.py`: MySQL/파일 사용자 조회
- `app/schemas.py`: UserProfile, ToolInput, AnswerContext
- `app/agent/service.py`: 질문마다 프로필 조회 후 도구/컨텍스트로 전달
- `app/agent/context.py`: 기본 정보·최근 대화·도구 결과 결합
- `app/integrations/ollama.py`: 모델 요청에 기본 정보 포함
- `scripts/import_users.py`: JSON → MySQL 등록/갱신
