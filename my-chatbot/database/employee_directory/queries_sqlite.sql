-- 사원 한 명의 기본 정보 / 연락처 / 사진
SELECT * FROM v_employee_profiles WHERE employee_id = 'KDN0001';

-- 현재 부서별 직원 목록
SELECT employee_id, name, department, job_title, extension_number, work_email
FROM v_employee_profiles WHERE dept_id = 'D001' AND employment_status = '재직'
ORDER BY employee_id;

-- 조직 현황. 상위 부서 정보는 원본에 있는 값만 사용합니다.
SELECT d.dept_id, d.dept_name, parent.dept_name AS parent_department,
       d.dept_function, d.location, d.main_extension,
       COUNT(p.employee_id) AS current_employee_count
FROM departments AS d
LEFT JOIN departments AS parent ON parent.dept_id = d.parent_dept_id
LEFT JOIN v_employee_profiles AS p ON p.dept_id = d.dept_id AND p.employment_status = '재직'
GROUP BY d.dept_id, d.dept_name, parent.dept_name, d.dept_function, d.location, d.main_extension
ORDER BY d.dept_id;

-- 사원 소속 이력
SELECT a.employee_id, e.name, d.dept_name, a.position_title, a.start_date, a.end_date, a.is_primary
FROM employee_assignments AS a
JOIN employees AS e ON e.employee_id = a.employee_id
JOIN departments AS d ON d.dept_id = a.dept_id
WHERE a.employee_id = 'KDN0001' ORDER BY a.start_date DESC;

-- 사원별 역할 이력. 실제 로그인 권한과는 별개입니다.
SELECT e.employee_id, e.name, r.role_name, r.role_category, er.start_date, er.end_date
FROM employee_roles AS er
JOIN employees AS e ON e.employee_id = er.employee_id
JOIN duty_roles AS r ON r.role_id = er.role_id
WHERE e.employee_id = 'KDN0001' ORDER BY er.start_date DESC;

-- 사내 공개 연락처 검색
SELECT employee_id, name, department, job_title, extension_number, work_email
FROM v_employee_profiles
WHERE contact_visibility = 'INTERNAL' AND (name LIKE '%서연%' OR department LIKE '%인사%')
ORDER BY employee_id;

-- 사진 준비 및 검수 상태
SELECT photo_status, photo_file_status, COUNT(*) AS employee_count
FROM employee_contacts GROUP BY photo_status, photo_file_status;
