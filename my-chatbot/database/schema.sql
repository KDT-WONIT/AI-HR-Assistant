-- python scripts/init_db.py가 .env의 DB를 선택한 뒤 실행합니다.

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

CREATE TABLE IF NOT EXISTS duty_roles (
    role_id VARCHAR(12) PRIMARY KEY,
    role_name VARCHAR(60) NOT NULL,
    role_category VARCHAR(30),
    description VARCHAR(250),
    security_level VARCHAR(20)
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

CREATE TABLE IF NOT EXISTS leave_balances (
    employee_id VARCHAR(50) NOT NULL,
    balance_year SMALLINT NOT NULL,
    granted_days DECIMAL(6,2) NOT NULL DEFAULT 0,
    used_days DECIMAL(6,2) NOT NULL DEFAULT 0,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (employee_id, balance_year),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

CREATE TABLE IF NOT EXISTS policy_documents (
    id CHAR(36) PRIMARY KEY,
    domain VARCHAR(64) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    version VARCHAR(50),
    effective_date DATE,
    file_path TEXT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    INDEX idx_document_domain (domain)
);

CREATE TABLE IF NOT EXISTS conversations (
    id CHAR(36) PRIMARY KEY,
    employee_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    created_at DATETIME(6) NOT NULL,
    ended_at DATETIME(6),
    end_result JSON,
    INDEX idx_conversation_employee (employee_id, created_at)
    -- 사번 확인/인증 정책은 별도 구현합니다.
);

CREATE TABLE IF NOT EXISTS messages (
    sequence_id BIGINT NOT NULL AUTO_INCREMENT UNIQUE,
    id CHAR(36) PRIMARY KEY,
    conversation_id CHAR(36) NOT NULL,
    role VARCHAR(20) NOT NULL,
    content LONGTEXT NOT NULL,
    sources JSON,
    tools_used JSON,
    context_data JSON,
    created_at DATETIME(6) NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    INDEX idx_message_recent (conversation_id, sequence_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id CHAR(36) NOT NULL UNIQUE,
    rating VARCHAR(20),
    comment TEXT,
    created_at DATETIME(6) NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS webhook_events (
    event_id CHAR(36) PRIMARY KEY,
    conversation_id CHAR(36) NOT NULL UNIQUE,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    attempts INT NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at DATETIME(6) NOT NULL,
    sent_at DATETIME(6),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
