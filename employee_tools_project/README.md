# 사원 규정 안내 Tool — 이동 가능한 프로젝트

이 폴더 전체를 팀원 PC에 복사하거나 ZIP으로 전달하면 됩니다. 개인 PC의 외부 DB 경로를 지정하지 않습니다.

## 폴더 구성

```text
employee_tools_project/
  README.md
  employee_tools/       Python Tool 5개, SQLite 연결, MCP 등록
  data/
    rag_data/          제공받은 규정 원문·파싱 자료·Chroma DB 포함
    employee/          팀원의 employee.sqlite3를 넣을 자리
  models/              최초 준비 시 bge-m3 모델을 내부에 저장
  .runtime/            모델·패키지 관련 내부 캐시
```

Windows에서는 Chroma 색인 제약 때문에 프로젝트 **전체 경로를 영문으로** 두세요. 폴더 이름이나 드라이브는 달라도 됩니다.

## 최초 한 번 준비

Python 3.11 이상이 설치된 터미널에서 이 README가 있는 폴더를 엽니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r employee_tools/requirements-mcp.txt --cache-dir .runtime/pip-cache
.\.venv\Scripts\python.exe -m employee_tools.prepare_model
```

모델은 처음 한 번 인터넷으로 받아 `models/bge-m3` 안에 저장합니다. 이후에는 외부 모델 캐시를 이용하지 않습니다. 내려받은 models 폴더까지 같이 옮기면 다음 PC에서는 모델을 다시 받을 필요가 없습니다. Python 가상환경 .venv는 PC마다 설치하세요.

## 사용자 DB 연결

팀원의 실제 DB를 `data/employee/employee.sqlite3`로 넣고 `employee_tools/sql_queries.json`의 테이블·컬럼을 맞추세요. 실제 사용자 DB는 아직 전달받지 않았으므로 ZIP에 포함되지 않았습니다. 규정 DB는 포함되어 있습니다.

## 실행 예

접속 시 받은 사원번호를 서버에서 전달합니다. 아래 번호는 사용법 예시이며 실제 등록 사원번호로 바꿉니다.

```powershell
.\.venv\Scripts\python.exe -m employee_tools.mcp_server --employee-id 000123
```

`EMPLOYEE_DB_PATH`나 `RAG_DATA_DIR` 같은 외부 파일 경로 설정은 사용하지 않습니다. 모든 기본 파일 경로는 이 프로젝트를 기준으로 자동 계산합니다.

Tool별 사용법·입출력·국내외 여비 적용 범위는 [상세 안내](employee_tools/README.md), 검증 범위는 [검증 기록](employee_tools/VALIDATION.md)을 참고하세요.
