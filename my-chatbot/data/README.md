# 데이터 넣는 곳

규정 PDF·CSV 폴더는 비어 있습니다. 파일을 넣어도 자동 적재되지는 않습니다.
`app/rag/`와 `scripts/ingest.py`를 구현한 뒤 적재합니다.
이 표의 경로는 기본값입니다. `.env`의 DATA_DIR·POLICY_DIR·CHROMA_DIR 등으로 변경할 수 있습니다.
9개 분야 도구도 설정된 POLICY_DIR을 사용합니다. 자세한 규칙은 docs/configuration.md를 참고하세요.

| 폴더 | 넣을 자료 |
| --- | --- |
| raw/policies/hr_employment | 인사 및 고용관리 PDF |
| raw/policies/work_labor | 근무 및 노사관리 PDF |
| raw/policies/pay_benefits | 급여 및 복리후생 PDF |
| raw/policies/contracts_finance | 계약 및 재무회계 PDF |
| raw/policies/audit_ethics | 감사 및 윤리준법 PDF |
| raw/policies/security_safety | 보안 및 안전관리 PDF |
| raw/policies/organization_management | 조직 및 경영관리 PDF |
| raw/policies/rnd_quality | 연구개발 및 품질 PDF |
| raw/policies/travel_expenses | 출장 및 여비 PDF |
| raw/csv | 가상 직원·휴가 등 원본 CSV |
| raw/users.json | 사용자 기본 정보. 예시 양식은 raw/users.example.json |
| processed/chunks | 추출·분할한 문서와 출처 메타데이터 JSON |
| vector_store/chroma | ChromaDB 로컬 저장 폴더 (구현 전) |
| models | 추후 임베딩 모델 캐시 |

PDF는 원본 파일명과 버전을 보존하세요. CSV 형식과 각 분야의 계산 규칙은 추후 정합니다.
ChromaDB에 임베딩·본문·출처 메타데이터를 함께 저장하도록 구현합니다.
원본 자료·생성 데이터는 `.gitignore`에 포함했습니다. 가상 데이터를 사용하세요.
