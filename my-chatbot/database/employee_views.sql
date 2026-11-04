-- 직원 한 명당 한 행. 현재 소속은 한국 날짜 기준으로 조회합니다.
-- 소속 기간이 잘못 중복되어도 결과가 여러 행이 되지 않게 최근 주 소속을 선택합니다.
CREATE OR REPLACE VIEW v_employee_profiles AS
SELECT e.employee_id, e.name, e.grade, e.hired_at,
       e.employment_type, e.employment_status,
       a.dept_id, COALESCE(d.dept_name, e.department) AS department,
       COALESCE(a.position_title, e.job_title) AS job_title,
       c.work_email, c.extension_number, c.work_location, c.contact_visibility,
       c.photo_path, c.photo_url, c.photo_status, c.photo_source, c.photo_alt,
       c.source_page_url, c.license_url, c.fallback_photo_path, c.photo_file_status
FROM employees AS e
LEFT JOIN employee_assignments AS a ON a.assignment_id = (
    SELECT current_assignment.assignment_id
    FROM employee_assignments AS current_assignment
    WHERE current_assignment.employee_id = e.employee_id
      AND current_assignment.is_primary = 1
      AND current_assignment.start_date <= DATE(UTC_TIMESTAMP() + INTERVAL 9 HOUR)
      AND (current_assignment.end_date IS NULL
           OR current_assignment.end_date >= DATE(UTC_TIMESTAMP() + INTERVAL 9 HOUR))
    ORDER BY current_assignment.start_date DESC, current_assignment.assignment_id DESC
    LIMIT 1
)
LEFT JOIN departments AS d ON d.dept_id = a.dept_id
LEFT JOIN employee_contacts AS c ON c.employee_id = e.employee_id;
