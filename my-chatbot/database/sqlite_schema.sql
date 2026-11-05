-- python scripts/init_db.py가 .env의 DB를 선택한 뒤 실행합니다.

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

CREATE TABLE IF NOT EXISTS duty_roles (
    role_id TEXT PRIMARY KEY,
    role_name TEXT NOT NULL,
    role_category TEXT,
    description TEXT,
    security_level TEXT
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

CREATE TABLE IF NOT EXISTS leave_balances (
    employee_id TEXT NOT NULL,
    balance_year SMALLINT NOT NULL,
    granted_days DECIMAL(6,2) NOT NULL DEFAULT 0,
    used_days DECIMAL(6,2) NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (employee_id, balance_year),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- 연차 원장 상세: leave_balances.granted_days = base_days + carryover_days + adjusted_days
CREATE TABLE IF NOT EXISTS leave_balance_details (
    employee_id TEXT NOT NULL,
    balance_year SMALLINT NOT NULL,
    base_days DECIMAL(6,2) NOT NULL DEFAULT 0,
    carryover_days DECIMAL(6,2) NOT NULL DEFAULT 0,
    adjusted_days DECIMAL(6,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (employee_id, balance_year),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- 연차·휴가 사용/신청 내역 (status: USED 사용 완료, APPROVED 승인(예정), PENDING 결재 중, CANCELLED 취소)
CREATE TABLE IF NOT EXISTS leave_transactions (
    transaction_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    leave_type TEXT NOT NULL,
    deducts_annual_leave SMALLINT NOT NULL DEFAULT 1,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    days DECIMAL(6,2) NOT NULL,
    status TEXT NOT NULL,
    requested_at TEXT,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);
CREATE INDEX IF NOT EXISTS idx_leave_transactions_employee ON leave_transactions(employee_id, start_date);

CREATE TABLE IF NOT EXISTS policy_documents (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    filename TEXT NOT NULL,
    version TEXT,
    effective_date TEXT,
    file_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    ended_at TEXT,
    end_result TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources TEXT,
    tools_used TEXT,
    context_data TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL UNIQUE,
    rating TEXT,
    comment TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS webhook_events (
    event_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INT NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

-- 직원 한 명당 한 행. 현재 소속은 한국 날짜 기준으로 조회합니다.
-- 소속 기간이 잘못 중복되어도 결과가 여러 행이 되지 않게 최근 주 소속을 선택합니다.
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

CREATE INDEX IF NOT EXISTS idx_message_recent ON messages(conversation_id, sequence_id);
CREATE INDEX IF NOT EXISTS idx_conversations_employee ON conversations(employee_id,created_at);
