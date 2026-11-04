# 직원 ID는 왜 모든 테이블에서 같아야 하나요?

## 기본 원칙
`employees.employee_id`는 직원 1명의 고유 식별자(PK)입니다. 연락처, 연차, 메신저 문의, 부서 소속 이력 등 다른 테이블에 등장하는 동일한 `employee_id`는 반드시 같은 직원 한 명을 참조합니다(FK).

단, **모든 테이블에 `employee_id`가 필요한 것은 아닙니다.** 규정은 `regulation_id`, 업무 주제는 `topic_id`, 부서는 `dept_id`로 연결됩니다. 예: `support_tickets.topic_id → business_topics.topic_id → topic_ownerships.topic_id → employees.employee_id`.

## 예시
- `employees`: KDN0001 = 김서연
- `employee_contacts`: KDN0001 = kdn0001@example.com, 내선 2101, 사진 `profiles/KDN0001.svg`
- `employee_assignments`: KDN0001 → D001(인사부)
- `leave_balances`: KDN0001의 2026년 부여 연차 16일

직원 소속과 업무 담당은 시간이 지나며 바뀔 수 있으므로 소속 이력은 `employee_assignments`에, 업무별 담당자 변경은 `topic_ownerships`의 유효기간으로 관리합니다. 같은 사번이라도 이전 소속 이력 행과 현재 소속 이력 행의 부서가 달라질 수 있는데, 이는 오류가 아니라 정상적인 이력입니다.

## FK 검사
`docs/fk_relationships.csv`에 모든 부모-자식 연결 관계가 나옵니다. `docs/validation_report.json`의 `fk_validation=PASS`는 생성된 CSV 간 연결의 유효성을 검증한 결과입니다. 실제 MySQL에 SQL 파일을 실행해 서버 DB 수준에서도 확인해야 합니다.
