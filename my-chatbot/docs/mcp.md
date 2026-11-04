# 로컬 MCP 도구 서버

공식 Python MCP SDK 2.3.0을 사용합니다. 실행은 기존처럼 프로젝트 루트에서 합니다.

```console
python -m pip install -r requirements.txt
python -m app --reload
```

FastAPI가 현재 Python으로 `python -m app.mcp.server`를 자동 실행하고 stdio 연결을 유지합니다.
앱을 종료하면 연결과 자식 프로세스도 종료합니다. 별도 포트·터미널·외부 MCP 서비스 설정은 필요 없습니다.
Windows reload의 Selector 루프에서는 MCP 통신만 별도 Proactor 스레드로 전달합니다.
`uvicorn main:app --reload`도 지원하지만 실행 방법 통일을 위해 위 모듈 명령을 권장합니다.

## 실제 채팅 경로

1. FastAPI에서 사용자·세션과 최근 대화를 조회합니다.
2. MCP `tools/list`에서 제공하는 현재 목록을 Ollama에 전달합니다.
3. Ollama가 선택한 ID와 인자를 검증합니다.
4. MCP `tools/call`로 해당 도구를 실행합니다.
5. MCP 서버가 사용자 프로필을 저장소에서 다시 조회하고 분야별 ChromaDB 검색·SQLite 업무 조회를 수행합니다.
6. 구조화된 ToolResult(문서·페이지·원문·계산 결과)를 받아 기존 답변 컨텍스트와 결합합니다.
7. Ollama 답변을 화면에 표시하고 세션에 저장합니다.

`app/tools`에 등록되는 도구가 MCP에도 자동 등록됩니다. 숫자 9를 고정하지 않습니다.
모든 현재 도구는 공통 `request` 인자를 받으며 question, employee_id, conversation_id, arguments를 포함합니다.
프로필 객체를 외부에서 주입할 수 없습니다. arguments는 year, requested_days, department를 검증합니다.
MCP 자체는 사용자 인증이 아닙니다. 현재 stdio 서버는 이 PC의 테스트용 호스트가 호출하는 구성입니다.

## 설정과 진단

- `.env`: `MCP_TIMEOUT_SECONDS=180` (첫 임베딩 모델 로딩 시간 포함)
- `GET /api/health`: tool_transport=mcp_stdio, integrations.mcp=ready
- 단독 MCP 서버: `python -m app.mcp.server` (stdio 클라이언트가 실행하는 명령)
- 실제 연결 검사: `python -m scripts.check_mcp`
- 실제 검색 검사:

```console
python -m scripts.check_mcp --tool pay_benefits --question "자녀 학자금 지원 기준은 무엇인가요?"
```

독립 MCP 클라이언트에서도 실행 파일에 사용할 Python의 절대 경로,
args에 `-m app.mcp.server`, cwd에 프로젝트 절대 경로를 지정하면 연결할 수 있습니다.
이 stdio 서버의 HTTP 주소는 없습니다.

연결·타임아웃·도구 실행 오류에는 503을 반환하고 질문/답변을 반쪽만 저장하지 않습니다.
직접 함수 실행으로 자동 우회하지 않습니다. 기존 단위 테스트만 LocalToolGateway를 명시적으로 사용합니다.

공식 SDK 안내: https://py.sdk.modelcontextprotocol.io/client/ , https://py.sdk.modelcontextprotocol.io/servers/tools/
