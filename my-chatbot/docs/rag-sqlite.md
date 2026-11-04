# SQLite + 기존 ChromaDB + Ollama

## 현재 연결

- 사원·부서·연락처·업무 역할: `database/employee_directory/employee_directory.sqlite3` (USER_DATA_SOURCE=directory)
- 대화·평가·연차 원장: `data/app.sqlite3` (SQLITE_PATH)
- 규정 벡터 DB: `chroma_db` (CHROMA_DIR)
- 컬렉션: `kdn_regulations_bge_m3_v1`, 59개 문서 / 7,117개 조각
- 질문 임베딩: `BAAI/bge-m3`, 리비전 `5617a9f61b028005a4858fdac845db406aefb181`, 1,024차원, 정규화
- 도구 선택: Ollama `qwen2.5:3b`, 최종 답변: `gemma3:4b` (각각 .env에서 변경 가능)

기존 ChromaDB는 재적재하지 않습니다. 컬렉션이 없으면 빈 컬렉션을 만들지 않고 오류를 반환합니다.
SQLite와 Chroma 내부 chroma.sqlite3는 서로 다른 DB입니다. 직원/대화를 Chroma 내부 DB에 쓰지 않습니다.
이전 MySQL DB는 삭제하지 않았으며 그 대화 기록을 자동 이관하지는 않습니다.

## 실행

현재 사용 중인 Python 3.13 환경에서 ChromaDB·Sentence Transformers를 확인했고 실제 검색도 검증했습니다.
다른 환경을 사용하면 먼저 의존성을 설치하세요.

```console
python -m pip install -r requirements.txt
python -m scripts.init_db
python -m app --reload
```

사원 배포본의 100명과 부서 16개를 직접 조회합니다. 화면 기본 사용자 ID는 KDN0001입니다.
사원 검색과 이미지 연결 방법은 employee-directory-integration.md를 참고하세요.
이전 SQLite 직원 테이블과 TEST-001/TEST-002 샘플은 남아 있지만 directory 설정의 사용자 원본은 독립 사원 DB입니다.
임베딩 모델은 `data/models`에 캐시합니다. 기존 모델의 이름·리비전·차원이 다르면 검색을 중단합니다.

## 요청 처리

1. ID로 SQLite 사용자 프로필과 해당 세션의 최근 메시지 최대 10개를 읽습니다.
2. MCP tools/list의 현재 도구 목록을 Ollama에 전달하고, JSON 스키마로 **하나**를 선택하게 합니다.
3. 모델이 반환한 ID와 연도/사용예정일수/부서 인자를 검증합니다.
4. MCP tools/call로 분야 문서만 검색합니다. 절차 질문은 원래 질문과 규정 표현으로 확장한 질문을 BGE-M3로 한 번에 임베딩하고 ChromaDB 결과를 통합·중복 제거합니다.
5. 거리 기준을 통과한 문서 조각에 문서명·페이지·조항·거리·조각 ID를 붙입니다.
6. 사용자 정보·최근 대화·검색 근거·업무 조회/계산 결과로 컨텍스트를 만듭니다.
7. 원문 문장에 근거 ID를 붙인 마크다운 문맥을 Ollama에 전달합니다. 모델이 근거 ID와 쉬운 설명을 반환하면 실제 문서·문장, 수치·부정 표현을 검증하고 요약·내용·출처·추가 안내를 출력합니다.
8. 질문과 답변을 SQLite에 한 트랜잭션으로 저장합니다.

문장 근거 ID는 서버가 원문에서 추출해 생성합니다. 모델이 원문을 다시 복사하며 문서 제목과 문장을 섞는 오류를 줄입니다.
설명에 새 수치·시스템명·반대 부정 표현이 생기는지 기본 검사를 수행합니다. 이 검사는 답변 의미 전체의 사실성을 보장하지 않습니다.
검사 실패 또는 잘린 JSON에는 짧은 확인 한계와 다음 단계를 표시하고 원문 전체를 답변에 붙이지 않습니다.
정확한 절차가 부족해도 관련 사용 기준이나 공통 제출 절차는 제공합니다. 관련 없는 휴직·특별휴가 절차를 연차 신청에 적용하지 않습니다.
각 검색 원문은 화면의 문서 근거를 펼쳐 확인할 수 있습니다. 기존 ChromaDB나 원문 파일을 재적재/변경하지 않습니다.
대화 컨텍스트에는 사용자 프로필·최근 메시지 최대 10개·도구 결과·검색 근거가 포함되며, 검색 원문은 중복 삽입하지 않습니다.
검색 자체가 근거 없음이면 답변 생성 모델을 호출하지 않고 담당자 확인을 안내합니다.
관련도 거리 기준 RAG_MAX_DISTANCE(기본 0.60)는 데이터별 조정이 필요한 값입니다.

## 분야 도구 기능

모든 분야 도구는 해당 규정 검색을 실제 수행합니다.

| 도구 | 검색 범위 / 추가 기능 |
| --- | --- |
| 인사 및 고용관리 | 인사·평가·승진·퇴직·고용 / 본인 기본 정보 조회 |
| 근무 및 노사관리 | 취업규칙·연차·휴직·노사·고충 / 잔여 연차 조회·사용 가정 계산 |
| 급여 및 복리후생 | 연봉·복지·사택·학자금·융자·임금피크 규정 |
| 계약 및 재무회계 | 계약·공정거래·회계·출자회사 규정 |
| 감사 및 윤리준법 | 감사·법무·내부통제·이해충돌·인권·윤리 규정 |
| 보안 및 안전관리 | 보안·안전·사고·배상·비상근무 규정 |
| 조직 및 경영관리 | 정관·직제·권한·문서·이사회 / 부서 목록 조회 |
| 연구개발 및 품질 | 연구개발·지식재산·품질 규정 |
| 출장 및 여비 | 국내외 출장·여비 규정 |

담당자/내선 질문은 해당 부서의 공개 범위가 INTERNAL인 업무 연락처를 SQLite에서 조회합니다.
급여 지급액이나 여비 액수를 임의 산출하거나 인사 변경·휴가 승인을 수행하지 않습니다.
확정된 수당/여비 계산 규칙과 추가 원장 데이터는 별도 구현 항목입니다.

## 연차 데이터

사원 정보만으로 연차 부여 일수를 추측하지 않습니다. 원장 데이터가 없으면 추가 정보 필요로 응답합니다.
CSV 열: employee_id, year, granted_days, used_days. 빈 양식은 data/raw/leave_balances.example.csv입니다.

```console
python -m scripts.import_leave_balances --file data/raw/leave_balances.csv
```

사용 가정 계산은 granted_days - used_days - requested_days이며 실제 원장은 변경하지 않습니다.
연도 미지정 시 한국 기준 현재 연도를 사용합니다. 초과 사용 가정은 sufficient=false로 반환합니다.

## 도구 추가/제거

`app/tools/`의 모듈에서 `tool = Tool(definition=..., execute=...)`를 내보내면 자동 등록됩니다.
ToolDefinition.source_patterns에 ChromaDB의 source 문서명에 포함될 패턴을 지정하세요.
등록 목록·선택 JSON 스키마·프론트 버튼·표시 개수는 목록에 맞춰 자동 반영됩니다.

```python
from app.schemas import ToolDefinition, ToolInput, ToolResult
from app.tools.base import Tool
from app.tools.execution import execute_domain
from app.config import settings

PATTERNS = ["새 분야 규정"]

async def execute(request: ToolInput) -> ToolResult:
    return await execute_domain("new_domain", PATTERNS, request)

tool = Tool(
    ToolDefinition(id="new_domain", name="새 분야", description="이 분야의 업무 설명",
                   data_path=str(settings.chroma_dir), source_patterns=PATTERNS),
    execute,
)
```

서버를 재시작하면 새 모듈이 반영됩니다. 파일을 제거하면 도구도 빠집니다.
ENABLED_TOOLS를 비우면 전체, 쉼표로 ID를 나열하면 그 도구만 활성화합니다.
등록되지 않은 ID나 중복 ID는 오류입니다. 현재 개수 9개를 코드 조건으로 사용하지 않습니다.

## API와 테스트

POST /api/chat 형식은 기존과 같습니다. tool_id를 지정하면 자동 선택을 건너뜁니다.
ToolResult.status: ok / no_result / needs_input / error.
ChatResponse.status: answered / no_result / needs_input.
context에는 user_profile, history, tool_results, sources가 포함됩니다.
Ollama 실패는 502, DB/임베딩/검색 실패는 503이며 다른 저장소나 모델로 조용히 대체하지 않습니다.

```console
python -m tests -v
python -m scripts.export_openapi
```

자동 테스트는 가짜 검색 결과/모델 응답과 임시 SQLite로 경계·상태를 확인합니다.
별도로 실제 기존 ChromaDB에서 모든 분야의 근거 반환과 59개 문서의 매핑을 확인했고,
설치된 Ollama를 통한 도구 선택·답변·근거 없음·SQLite 기록 복원을 확인했습니다.
실제 업무 질문 전체에 대한 답변 품질 평가를 대신하지는 않습니다.

구현에 참고한 계약: [Chroma Query API](https://docs.trychroma.com/reference/python/collection),
[Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs).
