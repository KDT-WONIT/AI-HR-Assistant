CREATE TABLE IF NOT EXISTS departments (
    dept_id TEXT PRIMARY KEY,
    dept_name TEXT NOT NULL UNIQUE,
    parent_dept_id TEXT,
    dept_function TEXT,
    location TEXT,
    main_extension TEXT,
    is_active TINYINT NOT NULL DEFAULT 1,
    FOREIGN KEY (parent_dept_id) REFERENCES departments(dept_id),
    CHECK (is_active IN (0, 1)),
    CHECK (parent_dept_id IS NULL OR parent_dept_id <> dept_id)
);

CREATE TABLE IF NOT EXISTS duty_roles (
    role_id TEXT PRIMARY KEY,
    role_name TEXT NOT NULL,
    role_category TEXT,
    description TEXT,
    security_level TEXT
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT,
    job_title TEXT,
    hired_at TEXT,
    grade TEXT,
    employment_type TEXT,
    employment_status TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employee_assignments (
    assignment_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    dept_id TEXT NOT NULL,
    position_title TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    is_primary TINYINT NOT NULL DEFAULT 1,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    FOREIGN KEY (dept_id) REFERENCES departments(dept_id),
    CHECK (is_primary IN (0, 1)),
    CHECK (end_date IS NULL OR end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS employee_roles (
    employee_role_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    FOREIGN KEY (role_id) REFERENCES duty_roles(role_id),
    CHECK (end_date IS NULL OR end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS employee_contacts (
    employee_id TEXT PRIMARY KEY,
    work_email TEXT UNIQUE,
    extension_number TEXT,
    work_location TEXT,
    contact_visibility TEXT NOT NULL DEFAULT 'INTERNAL',
    photo_path TEXT,
    photo_url TEXT,
    photo_status TEXT NOT NULL DEFAULT 'REVIEW_PENDING',
    photo_source TEXT,
    photo_alt TEXT,
    source_page_url TEXT,
    license_url TEXT,
    fallback_photo_path TEXT,
    photo_file_status TEXT NOT NULL DEFAULT 'NOT_DOWNLOADED',
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

CREATE VIEW IF NOT EXISTS v_employee_profiles AS
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
      AND current_assignment.start_date <= date('now', '+9 hours')
      AND (current_assignment.end_date IS NULL
           OR current_assignment.end_date >= date('now', '+9 hours'))
    ORDER BY current_assignment.start_date DESC, current_assignment.assignment_id DESC
    LIMIT 1
)
LEFT JOIN departments AS d ON d.dept_id = a.dept_id
LEFT JOIN employee_contacts AS c ON c.employee_id = e.employee_id;
