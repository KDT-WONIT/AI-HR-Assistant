# 모듈 실행 방법

모든 명령은 가상환경을 활성화하고 **my-chatbot 프로젝트 폴더**에서 실행합니다.
`app`, `tests`, `scripts`는 각각 `__init__.py`를 가진 Python 패키지입니다.

## 서버

```console
python -m app --reload
```

기본 주소는 http://127.0.0.1:8000/ 입니다. 다른 포트는 `--port 8001`을 추가합니다.
기존 `python -m uvicorn app.main:app --reload` 또는 `main:app` 진입점도 유지합니다.

## 테스트

```console
# 질문에 나온 API 테스트만 실행
python -m tests.test_api -v

# 같은 테스트를 표준 unittest 명령으로 실행
python -m unittest tests.test_api -v

# 전체 테스트
python -m tests -v

# 설정/사용자 컨텍스트 테스트만 선택
python -m unittest tests.test_config tests.test_users -v
```

`tests`는 `app/tests`가 아니라 프로젝트 루트의 별도 패키지입니다.
`python tests/test_api.py`와 같은 파일 경로 실행 대신 위 모듈 명령을 사용하세요.
파일 경로로 실행하면 Python이 tests 폴더를 검색 시작 위치로 삼아 형제 패키지 app을 찾지 못할 수 있습니다.
모듈 실행은 프로젝트 루트에서 패키지 이름을 찾아 실행합니다.

MySQL·Ollama 통합 테스트는 별도 설정이 있을 때만 실행합니다. 설정은 docs/testing.md를 참고하세요.

## 관리 명령

```console
python -m scripts.show_paths
python -m scripts.export_openapi
python -m scripts.init_db
python -m scripts.import_users --file data/raw/users.json
python -m scripts.seed_employees --check-only
python -m scripts.seed_employees
python -m scripts.build_employee_directory --output-dir database/employee_directory_new
python -m scripts.ingest --domain work_labor
```

마지막 문서 적재 명령은 아직 구현 전으로 안내 메시지를 반환합니다.
현재 DB 초기화/데이터 적재 명령은 `.env`의 SQLITE_PATH에 지정한 SQLite 파일을 사용합니다.
실제 RAG/도구 구현과 연차 적재 명령은 docs/rag-sqlite.md를 참고하세요.
관리 모듈은 import만 했을 때 실행되거나 파일을 쓰지 않고, main()으로 실행 동작을 분리했습니다.

## 환경 확인

```console
python -c "import sys; print(sys.executable)"
python -m pip install -r requirements-dev.txt
```

현재 활성화한 환경의 Python을 사용합니다. 이 프로젝트의 `.venv`를 직접 쓰려면
위 명령의 `python`을 `.\.venv\Scripts\python.exe`로 바꾸면 됩니다.
