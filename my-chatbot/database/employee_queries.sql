-- scripts/init_db.py → scripts/seed_employees.py 실행 후 선택한 DB에서 사용합니다.

-- 1. 사번으로 기본 사용자 정보 조회
SELECT employee_id, name, grade, hired_at, employment_type, employment_status,
       department, job_title, work_email, extension_number, work_location,
       photo_path, photo_url, photo_status, photo_file_status,
       fallback_photo_path, source_page_url, license_url
FROM v_employee_profiles
WHERE employee_id = 'KDN0001';

-- 2. 인사부 현재 재직자와 사내 공개 연락처
SELECT employee_id, name, department, job_title, extension_number, work_email
FROM v_employee_profiles
WHERE dept_id = 'D001' AND employment_status = '재직' AND contact_visibility = 'INTERNAL'
ORDER BY employee_id;

-- 3. 사용자의 현재 업무 역할 (로그인 권한과는 별개)
SELECT e.employee_id, e.name, r.role_name, r.role_category, r.description
FROM employees AS e
JOIN employee_roles AS er ON er.employee_id = e.employee_id
JOIN duty_roles AS r ON r.role_id = er.role_id
WHERE e.employee_id = 'KDN0001'
  AND er.start_date <= DATE(UTC_TIMESTAMP() + INTERVAL 9 HOUR)
  AND (er.end_date IS NULL OR er.end_date >= DATE(UTC_TIMESTAMP() + INTERVAL 9 HOUR));

-- 4. 소속 이력
SELECT a.employee_id, d.dept_name, a.position_title, a.start_date, a.end_date, a.is_primary
FROM employee_assignments AS a
JOIN departments AS d ON d.dept_id = a.dept_id
WHERE a.employee_id = 'KDN0001'
ORDER BY a.start_date DESC;

-- 5. 사용자와 기존 대화·평가 연결 (사번을 공통 키로 사용)
SELECT c.id AS conversation_id, c.employee_id, e.name, c.created_at,
       c.status, f.rating, f.comment
FROM conversations AS c
LEFT JOIN employees AS e ON e.employee_id = c.employee_id
LEFT JOIN feedback AS f ON f.conversation_id = c.id
WHERE c.employee_id = 'KDN0001'
ORDER BY c.created_at DESC;

-- 6. 사진 검수/다운로드 진행 상태
SELECT photo_status, photo_file_status, COUNT(*) AS employee_count
FROM employee_contacts
GROUP BY photo_status, photo_file_status;
