# 로컬 MySQL 저장과 최근 대화 컨텍스트

## 설정

프로젝트 폴더에서 `.env.example`을 `.env`로 복사하고 로컬 접속정보를 채웁니다.
이미 `.env`가 있다면 해당 파일만 수정하세요. 비밀번호는 이 파일에만 보관합니다.

```dotenv
APP_MODE=demo
STORAGE_BACKEND=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=ai_hr_assistant
MYSQL_USER=root
MYSQL_PASSWORD=로컬_MySQL_비밀번호
HISTORY_MESSAGE_LIMIT=10
ANSWER_PROVIDER=demo
```

MySQL 사용자 계정은 미리 존재해야 합니다. 초기화 시 해당 계정의 DB·테이블·뷰 생성 및 테이블 변경 권한이 필요합니다.
현재 PC의 MySQL 서비스를 사용하며, 이 프로젝트가 기존 서비스나 계정의 비밀번호를 바꾸지는 않습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe -m app --reload
```

이미 서버가 실행 중이면 종료 후 다시 실행하세요. `.env` 수정은 서버 재시작 후 적용됩니다.
초기화는 DB/테이블이 없으면 생성하고 이전 뼈대에 필요한 컬럼을 추가합니다. 기존 기록은 삭제하지 않습니다.
`GET /api/health`에서 `storage=mysql`, `storage_status=ready`이면 준비된 상태입니다.
접속 오류·미초기화 상태에서 저장을 시도하면 `503`을 반환하며 메모리로 전환하지 않습니다.

아직 로컬 DB 계정/비밀번호를 준비하지 않았다면 `STORAGE_BACKEND=memory`로 화면을 확인할 수 있습니다.
이 모드에서는 서버 재시작 후 기록이 사라집니다. 메모리의 기존 기록을 MySQL로 자동 이관하지는 않습니다.

## 저장 단위

- `employee_id`: 가상 직원 식별값
- `conversation_id`: 대화마다 발급하는 UUID. 동일 사번도 새 대화를 시작하면 별도 세션입니다.
- `messages`: 사용자 질문과 AI 답변 각각 한 행. 역할·본문·시각·출처·사용 도구를 보관합니다.
- AI 답변 행의 `context_data`: 해당 답변에 사용한 최근 대화·도구 결과·출처
- `feedback`: 대화 종료 시 선택한 평가/의견
- `webhook_events`: 종료 이벤트. 실제 n8n 전송은 아직 하지 않습니다.

정상 답변이 생성된 후 질문과 답변을 한 트랜잭션으로 저장하고 반환합니다.
모델 오류나 저장 오류 시에는 질문/답변 반쪽 기록을 남기지 않습니다. 실패 요청 자체의 로그는 별도 기능입니다.
동시 질문에서 이전 대화가 바뀌었으면 `409`로 알려 오래된 컨텍스트의 답변 저장을 방지합니다.

## 최근 대화 조회

답변 생성 시 현재 세션 ID로 다음과 같이 조회합니다.

```sql
SELECT * FROM messages
WHERE conversation_id = %s
ORDER BY sequence_id DESC
LIMIT %s;
```

최신 N개만 읽은 뒤 오래된 순서로 뒤집어 컨텍스트에 전달합니다.
`HISTORY_MESSAGE_LIMIT`은 **5~10개 메시지**입니다. 사용자 질문과 AI 답변을 각각 1개로 세며,
기본 10개는 약 5번의 왕복 대화입니다. 현재 질문은 이전 기록에 중복해서 넣지 않습니다.
다른 세션이나 같은 사번의 다른 대화는 포함하지 않습니다. 전체 기록은 DB에 계속 남습니다.

## Ollama 사용

설치된 모델 이름을 지정하고 답변 제공자를 바꿉니다. 모델을 자동 다운로드하지 않습니다.

```dotenv
ANSWER_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=설치한_모델_이름
OLLAMA_TIMEOUT_SECONDS=60
```

Ollama의 `/api/chat`에 `system → DB 최근 대화 → 현재 질문과 도구 결과` 순서로 전송합니다.
DB 저장과 답변 제공자는 독립적이므로 MySQL + 모의 답변, MySQL + Ollama 모두 사용할 수 있습니다.
분야별 실제 규정 검색·계산과 LLM 도구 선택은 여전히 구현 전입니다.
Ollama HTTP 오류·빈 응답·타임아웃은 `502`로 알립니다.

## 기록 확인

```sql
SELECT c.employee_id, m.conversation_id, m.role, m.content, m.created_at
FROM messages AS m
JOIN conversations AS c ON c.id = m.conversation_id
ORDER BY m.sequence_id DESC
LIMIT 30;
```

접속정보와 실제 모델이 없으므로 배포 대상 DB·실제 모델의 답변 품질은 아직 검증하지 않았습니다.
별도의 임시 MySQL과 로컬 Ollama HTTP 모의 서버로 통합 동작을 검증했습니다.

연동 계약 참고: [MySQL Connector/Python 연결](https://dev.mysql.com/doc/connector-python/en/connector-python-connectargs.html),
[Ollama Chat API](https://github.com/ollama/ollama/blob/main/docs/api.md).
