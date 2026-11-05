# 사원·부서·연락처·이미지 연동

## 연결된 데이터

- 원본: `database/employee_directory/employee_directory.sqlite3`
- 사원 100명, 부서 16개, 소속·업무 역할·연락처·사진 메타데이터
- 기본 프로필 아이콘: `database/employee_directory/assets/profiles/`의 SVG 100개
- 대화·평가·연차 원장: 기존 `data/app.sqlite3`

독립 사원 DB를 읽기 전용으로 직접 조회합니다. 기존 대화 DB를 교체하거나 사원 배포본에 대화 테이블을 만들지 않습니다.
사번 조회·MCP의 사원/연락처/부서 도구·화면 검색이 같은 DB를 사용합니다.
소속과 업무 역할은 시작일·종료일을 한국 날짜 기준으로 확인합니다.

## 설정

```dotenv
USER_DATA_SOURCE=directory
EMPLOYEE_DIRECTORY_DIR=./database/employee_directory
```

DB 파일 이름이 다르면 `EMPLOYEE_DIRECTORY_DB`에 파일 경로를 별도로 지정할 수 있습니다.
기본값은 EMPLOYEE_DIRECTORY_DIR 아래 employee_directory.sqlite3입니다.
설정 경로 변경은 서버 재시작 후 적용됩니다. 같은 DB 안의 사원·소속·연락처 수정은 다음 조회부터 반영됩니다.
DB가 없으면 빈 DB를 자동 생성하지 않고 연결 오류를 안내합니다.
연차 원장 CSV 등록 시에는 독립 사원 DB의 사번을 확인한 후 대화 DB에 필요한 사번 참조 행만 추가합니다.
원장의 외래키를 보존하기 위한 처리이며 프로필 원본은 계속 독립 사원 DB를 사용합니다.

## 화면

1. 사번을 입력하면 이름·소속·직무·직급·이메일·내선·근무지·업무 역할과 프로필 이미지를 표시합니다.
2. **사원·부서 찾기**에서 이름·사번·부서 검색과 부서별 필터를 사용할 수 있습니다.
3. 부서 선택에는 현재 인원·위치·대표 내선이 표시됩니다.
4. 검색된 사원의 **이 사번으로 새 대화**를 누르면 해당 사용자로 새 세션을 준비합니다.

기존 대화의 사번을 중간에 바꾸지는 않습니다. 새 대화를 선택하면 이전 대화 기록은 DB에 남아 있습니다.

## 챗봇 컨텍스트와 도구

현재 사용자의 기본 정보에 부서 기능·부서 대표 내선·업무 이메일·개인 내선·근무지·업무 역할을 추가했습니다.
MCP 서버도 사원 DB에서 현재 프로필을 다시 읽습니다.

예시 질문:

- 내 정보와 내 이메일, 내 내선을 알려줘
- 김서연 연락처 알려줘
- 인사부 대표 내선 알려줘
- 부서 목록과 부서별 인원 알려줘

사원 정보만 묻는 질문은 DB 조회 결과를 그대로 정리하여 제공합니다. 무관한 규정 검색이나 LLM 추측을 섞지 않습니다.
규정 질문에서는 기존 RAG 흐름에 사용자 정보를 포함합니다. 업무 역할은 로그인 권한이나 휴가 승인 자격을 뜻하지 않습니다.

## API

| API | 내용 |
| --- | --- |
| GET /api/users/{사번} | 기본 프로필·부서·연락처·업무 역할·로컬 image_url |
| GET /api/users/{사번}/photo | 해당 사원의 허용된 로컬 이미지 |
| GET /api/employees?query=김서연&department_id=D001&limit=12&offset=0 | 사원 검색·부서 필터·페이지 조회 |
| GET /api/departments | 부서 정보와 현재 소속 인원 |

검색 결과는 items, total, limit, offset으로 반환됩니다. 한 번에 최대 50명을 요청할 수 있습니다.
contact_visibility가 INTERNAL이 아니면 개인 이메일·내선·근무지를 응답에서 숨깁니다.
현재 사번 입력은 테스트 식별 방식이며 별도의 로그인 인증을 대신하지 않습니다.

## 이미지 선택

현재 Pexels 원본 JPG는 파일이 없고 REVIEW_PENDING / NOT_DOWNLOADED입니다.
포함된 기본 아이콘을 표시하며 외부 사진 URL을 자동 요청하거나 다운로드하지 않습니다.
승인된 사진 파일을 쓰려면 assets 아래에 파일을 두고 photo_path, photo_status=APPROVED,
photo_file_status=AVAILABLE(또는 DOWNLOADED/LOCAL)를 설정하면 됩니다. 조건을 충족하지 않으면 fallback_photo_path를 사용합니다.
이미지 API는 assets 안의 SVG/PNG/JPG/JPEG/WebP만 반환하고 DB·SQL 파일이나 상위 폴더는 공개하지 않습니다.

## 추가 구현과 이유

| 구현 | 이유 |
| --- | --- |
| 독립 읽기 전용 저장소와 환경변수 | 원본을 직접 관리하면서 대화 기록을 보존하기 위해 |
| 프로필·역할·연락처·부서 정보의 공통 조회 | 화면과 에이전트가 서로 다른 직원 정보를 쓰지 않도록 |
| 사원 검색·부서 필터·프로필 카드 | 제공된 이름·소속·연락처·이미지를 서비스에서 확인할 수 있도록 |
| 로컬 이미지 전용 API·기본 아이콘 | 실제 사진 파일이 없는 현재 자료를 표시하고 DB 파일 노출을 방지하기 위해 |
| 순수 사원 조회의 RAG 생략 | 연락처 답변에 관련 없는 규정과 불필요한 생성 문장이 섞이지 않도록 |
| 일반 API 테스트의 외부 웹훅 분리 | 개발자 환경에 설정된 n8n으로 테스트 평가가 전송되지 않도록 |
| 연차 원장의 사번 참조 호환 처리 | 깨끗한 대화 DB에서도 독립 사원 DB에 등록된 직원의 연차 원장을 넣을 수 있도록 |

## 확인 결과

연동·설정·기존 SQLite 호환 검사 20개가 통과했습니다.
실제 서비스에서 사원 100명·부서 16개·프로필 SVG 응답을 확인했고,
화면에서 이준호(WON0002)를 찾아 선택한 뒤 해당 사용자의 이메일·내선·역할로 답변하는 것을 확인했습니다.
인사부의 대표 내선 2010·위치 본사·인원 7명도 사원 DB 조회 결과와 일치했습니다.
광범위한 기존 테스트 재실행에서는 앞서 기록된 Windows 소켓 생성 오류가 재현되었으며,
이 연동 전용 API 검사는 MCP 수명 주기와 분리해 읽기 전용 API 경계를 검사합니다.

## 사원 사진 표시

`/api/users/{사번}/photo`는 다음 순서로 사진을 제공합니다.

1. `database/employee_directory/assets/photos/{사번}.jpg`가 있으면 그 파일 (기본은 검수 상태와 무관, `EMPLOYEE_PHOTO_REQUIRE_APPROVAL=true`이면 APPROVED만)
2. 없으면 사원 DB `employee_contacts.photo_url`로 307 이동 — `https://images.pexels.com`만 허용하며 브라우저가 직접 불러옵니다 (`EMPLOYEE_PHOTO_REMOTE=false`로 끔)
3. 불러오기 실패 시 화면이 `?fallback=true`로 로컬 SVG 아이콘을 다시 요청하고, 그것도 실패하면 이름 첫 글자

오프라인에서도 쓰려면 인터넷이 되는 PC에서 한 번 실행합니다.

```console
python -m scripts.download_employee_photos            # 없는 사진만
python -m scripts.download_employee_photos --force    # 전체 다시
```

사진은 가상 직원용 스톡 사진(Pexels)이며 카드의 사진에 마우스를 올리면 "실제 직원 아님" 안내(photo_alt)가 표시됩니다.
