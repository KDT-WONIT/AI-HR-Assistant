-- 실제 사용자 DB의 구조를 추정한 파일이 아닙니다. 팀원과 SQL 매핑을 협의하기 위한 예시입니다.
-- 기존 DB에 실행할 필요 없이 sql_queries.json의 SELECT ... AS ... 로 컬럼을 맞춰도 됩니다.
CREATE TABLE employees (
    employee_id TEXT PRIMARY KEY, name TEXT NOT NULL, department TEXT NOT NULL,
    job_title TEXT, travel_grade TEXT NOT NULL
    -- travel_grade: executive / grade_1 / grade_2 / grade_3 / grade_4_plus
);
CREATE TABLE leave_balances (
    employee_id TEXT NOT NULL, leave_type TEXT NOT NULL,
    period_start TEXT NOT NULL, period_end TEXT NOT NULL,
    granted_days NUMERIC NOT NULL, carried_days NUMERIC NOT NULL DEFAULT 0,
    adjustment_days NUMERIC NOT NULL DEFAULT 0, expired_days NUMERIC NOT NULL DEFAULT 0,
    PRIMARY KEY (employee_id, leave_type, period_start)
);
CREATE TABLE leave_usage (
    usage_id INTEGER PRIMARY KEY, employee_id TEXT NOT NULL, leave_type TEXT NOT NULL,
    used_on TEXT NOT NULL, days NUMERIC NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('approved', 'pending', 'cancelled', 'rejected'))
    -- 휴일 차감이 끝난 날짜별 차감량: 전일 1, 반일 0.5, 반반일 0.25 등.
);
CREATE TABLE contacts (
    contact_id INTEGER PRIMARY KEY, name TEXT NOT NULL, department TEXT NOT NULL,
    topic TEXT NOT NULL, keywords_json TEXT NOT NULL DEFAULT '[]',
    phone TEXT, email TEXT, is_active INTEGER NOT NULL DEFAULT 1
    -- topic='general'은 DB에 명시적으로 지정한 일반 문의 담당자입니다.
);
CREATE TABLE inquiries (
    inquiry_id INTEGER PRIMARY KEY, employee_id TEXT NOT NULL,
    question TEXT NOT NULL, answer TEXT, category TEXT, created_at TEXT NOT NULL, status TEXT
);
CREATE INDEX idx_leave_usage_owner ON leave_usage(employee_id, leave_type, used_on);
CREATE INDEX idx_inquiries_owner ON inquiries(employee_id, created_at);
