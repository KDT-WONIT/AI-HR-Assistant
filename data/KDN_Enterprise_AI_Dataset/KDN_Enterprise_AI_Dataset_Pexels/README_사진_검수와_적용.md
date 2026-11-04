# 전사 AI 챗봇 100명 스톡사진 후보 업데이트 (Pexels)

## 현재 제공하는 것
- 100명의 기존 사번(고유 employee_id)을 **변경하지 않고**, 직무를 참고한 서로 다른 Pexels 사진 **100개 후보 URL**을 매핑했습니다.
- `docs/employee_photo_manifest_100.csv`: 사번, 직원명, 부서, 사진 URL, Pexels 출처, 검수 상태 100행.
- `sql/04_update_100_pexels_photos.sql`: 이미 MySQL에 적재한 100명 사진 필드 업데이트.
- `sql/02_seed_data.sql`, `csv/employee_contacts.csv`: 신규 설치 시에도 일치하도록 사진 관련 값 수정.
- `100명_스톡사진_검수갤러리.html`: 브라우저에서 사진을 보고 승인/교체 필요를 저장한 뒤 검수 결과 CSV 내보내기.
- `download_photos_and_validate.py`: **인터넷 연결된 Windows/PyCharm**에서 승인한 사진을 다운로드하고, 파일 크기·포맷·중복 검사. 실행 후 로컬 JPG 파일 생성.
- `README_사진_검수와_적용.md`: 단계별 적용 가이드.

## 중요: 무엇이 아직 검증되지 않았나?
- 웹 검색 결과의 제목/설명/라이선스를 확인하여 후보를 선별했고, 각각 고유한 Pexels 사진 페이지 ID를 사용했지만 **100장 원본을 열어 눈으로 개별 검수하거나 이미지 CDN 100건의 응답을 실제 다운로드하여 검증하지는 못했습니다.**
- 이 패키지 ZIP에는 **사진 JPG 원본 100장은 아직 포함되지 않습니다.** 사진 파일은 네트워크 사용이 가능한 환경에서 `download_photos_and_validate.py`를 실행해 생성해야 합니다.
- `REVIEW_PENDING`은 검수 대기 상태입니다. 승인(저작권 및 초상권 검토 포함) 전 실서비스에 사용하지 마세요.
- Pexels 사진 라이선스: https://www.pexels.com/license/ , 인물의 허위 소속/추천·보증을 암시하는 사용은 주의해야 합니다.

## 기존 DB 업데이트 (Workbench)
1. `sql/04_update_100_pexels_photos.sql` 파일 실행 (기존 스키마 및 데이터 유지)
2. 실행 확인:
```sql
USE enterprise_ai_agent;
SELECT COUNT(*) FROM employee_contacts WHERE photo_source = 'PEXELS_STOCK_DEMO';
SELECT employee_id, photo_url, photo_status FROM employee_contacts LIMIT 10;
```
3. CSV 갤러리에서 승인/교체를 판단하고, 필요한 사진을 교체.

## 새 DB 생성
`01_create_schema.sql` → `02_seed_data.sql` 순으로 실행하면 신규 주소가 입력됩니다. 구버전 `04_OLD_randomuser_do_not_run.sql`은 **사용하지 않습니다**.

## 로컬 사진 생성 (인터넷 연결 PC)
PyCharm Terminal에서:
```bash
python -m pip install requests pillow
python download_photos_and_validate.py
```
다운로드 완료 후 `assets/photos/KDN0001.jpg` 등으로 고정합니다. FastAPI에서 `app.mount('/photos',StaticFiles(directory='assets/photos'),name='photos')`를 등록하면, 웹 UI에서는 `/photos/KDN0001.jpg` 같은 내부 서버 URL을 사용하면 됩니다.

## 사진 정책
동일 파일명/사번 1:1, 서로 다른 원본사진 ID 100개, 출처 페이지·용도·검수상태 보존. 가상 회사 직원 카드에는 반드시 ‘가상 직원 / 스톡사진’ 고지.
