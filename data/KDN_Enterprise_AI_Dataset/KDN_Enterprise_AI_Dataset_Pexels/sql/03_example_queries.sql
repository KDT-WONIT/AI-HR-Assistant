-- Query examples for MySQL Workbench; run after 01 and 02.
USE enterprise_ai_agent;

-- 1. Dataset counts
SELECT COUNT(*) AS employees FROM employees;
SELECT COUNT(*) AS regulations FROM regulations;
SELECT COUNT(*) AS topics FROM business_topics;
SELECT COUNT(*) AS contact_cards FROM v_topic_contact_cards;

-- 2. Search official-looking directory: all fictional
SELECT * FROM v_employee_directory ORDER BY employee_id LIMIT 20;

-- 3. Employee KDN0001 leave remaining; year 2026
SELECT * FROM v_leave_balance WHERE employee_id='KDN0001' AND `year`=2026;

-- 4. Query business-topic contact card by keyword
SELECT DISTINCT c.topic_name,c.dept_name,c.employee_name,c.extension_number,c.work_email,c.photo_path
FROM topic_keywords k JOIN v_topic_contact_cards c ON c.topic_id=k.topic_id
WHERE k.keyword LIKE '%사택%' LIMIT 20;

-- 5. Topic and its source article + document title
SELECT t.topic_name,r.title,a.article_number,a.article_title,a.page_number
FROM business_topics t JOIN topic_regulations tr ON tr.topic_id=t.topic_id
JOIN regulation_articles a ON a.article_id=tr.article_id
JOIN regulation_versions v ON v.version_id=a.version_id
JOIN regulations r ON r.regulation_id=v.regulation_id
WHERE t.topic_name LIKE '%주택자금 융자%' LIMIT 10;

-- 6. Support tickets and assigned fictional employees
SELECT s.ticket_id,s.status,e.employee_name AS requester,o.employee_name AS assignee,t.topic_name
FROM support_tickets s JOIN employees e ON e.employee_id=s.employee_id
JOIN employees o ON o.employee_id=s.owner_employee_id
JOIN business_topics t ON t.topic_id=s.topic_id LIMIT 15;

-- 7. Only demo: never use employee-id entry alone to authorize sensitive access.
SELECT COUNT(*) AS restricted_topics FROM business_topics WHERE security_level='RESTRICTED';
