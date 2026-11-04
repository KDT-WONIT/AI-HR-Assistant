-- 독립 사원/조직 DB. 앱의 기본 DB와 별도로 생성합니다.
CREATE DATABASE IF NOT EXISTS `employee_directory` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `employee_directory`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS departments (
    dept_id VARCHAR(12) PRIMARY KEY,
    dept_name VARCHAR(80) NOT NULL UNIQUE,
    parent_dept_id VARCHAR(12),
    dept_function VARCHAR(200),
    location VARCHAR(80),
    main_extension VARCHAR(12),
    is_active TINYINT NOT NULL DEFAULT 1,
    FOREIGN KEY (parent_dept_id) REFERENCES departments(dept_id),
    CHECK (is_active IN (0, 1)),
    CHECK (parent_dept_id IS NULL OR parent_dept_id <> dept_id)
);

CREATE TABLE IF NOT EXISTS duty_roles (
    role_id VARCHAR(12) PRIMARY KEY,
    role_name VARCHAR(60) NOT NULL,
    role_category VARCHAR(30),
    description VARCHAR(250),
    security_level VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    department VARCHAR(100),
    job_title VARCHAR(100),
    hired_at DATE,
    grade VARCHAR(25),
    employment_type VARCHAR(30),
    employment_status VARCHAR(20),
    created_at DATETIME(6) NOT NULL
);

CREATE TABLE IF NOT EXISTS employee_assignments (
    assignment_id VARCHAR(14) PRIMARY KEY,
    employee_id VARCHAR(50) NOT NULL,
    dept_id VARCHAR(12) NOT NULL,
    position_title VARCHAR(60) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    is_primary TINYINT NOT NULL DEFAULT 1,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    FOREIGN KEY (dept_id) REFERENCES departments(dept_id),
    INDEX idx_assignment_employee (employee_id, is_primary, start_date, end_date),
    CHECK (is_primary IN (0, 1)),
    CHECK (end_date IS NULL OR end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS employee_roles (
    employee_role_id VARCHAR(14) PRIMARY KEY,
    employee_id VARCHAR(50) NOT NULL,
    role_id VARCHAR(12) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    FOREIGN KEY (role_id) REFERENCES duty_roles(role_id),
    INDEX idx_employee_role (employee_id, start_date, end_date),
    CHECK (end_date IS NULL OR end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS employee_contacts (
    employee_id VARCHAR(50) PRIMARY KEY,
    work_email VARCHAR(130) UNIQUE,
    extension_number VARCHAR(12),
    work_location VARCHAR(100),
    contact_visibility VARCHAR(25) NOT NULL DEFAULT 'INTERNAL',
    photo_path VARCHAR(260),
    photo_url VARCHAR(500),
    photo_status VARCHAR(30) NOT NULL DEFAULT 'REVIEW_PENDING',
    photo_source VARCHAR(40),
    photo_alt VARCHAR(150),
    source_page_url VARCHAR(500),
    license_url VARCHAR(500),
    fallback_photo_path VARCHAR(260),
    photo_file_status VARCHAR(30) NOT NULL DEFAULT 'NOT_DOWNLOADED',
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

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
