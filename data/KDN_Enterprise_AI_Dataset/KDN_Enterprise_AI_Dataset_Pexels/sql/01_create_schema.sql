-- Educational mock data. All employees, emails and records are fictional.
-- MySQL 8.0+ / 8.4; safe UTF-8, foreign keys enabled.
CREATE DATABASE IF NOT EXISTS `enterprise_ai_agent` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `enterprise_ai_agent`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `business_topics` (
  `topic_id` VARCHAR(12) NOT NULL,
  `topic_name` VARCHAR(200) NULL,
  `category` VARCHAR(40) NULL,
  `description` TEXT NULL,
  `intent_type` VARCHAR(30) NULL,
  `security_level` VARCHAR(25) NULL,
  `auto_answer_allowed` TINYINT NULL,
  PRIMARY KEY (`topic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `departments` (
  `dept_id` VARCHAR(12) NOT NULL,
  `dept_name` VARCHAR(80) NULL,
  `parent_dept_id` VARCHAR(12) NULL,
  `dept_function` VARCHAR(200) NULL,
  `location` VARCHAR(80) NULL,
  `main_extension` VARCHAR(12) NULL,
  `is_active` TINYINT NULL,
  PRIMARY KEY (`dept_id`),
  UNIQUE KEY `uq_departments_1_0` (`dept_name`),
  CONSTRAINT `fk_departments_parent_dept_id` FOREIGN KEY (`parent_dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `duty_roles` (
  `role_id` VARCHAR(12) NOT NULL,
  `role_name` VARCHAR(60) NULL,
  `role_category` VARCHAR(30) NULL,
  `description` VARCHAR(250) NULL,
  `security_level` VARCHAR(20) NULL,
  PRIMARY KEY (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `employees` (
  `employee_id` VARCHAR(12) NOT NULL,
  `employee_name` VARCHAR(40) NULL,
  `grade` VARCHAR(25) NULL,
  `hire_date` DATE NULL,
  `employment_type` VARCHAR(30) NULL,
  `employment_status` VARCHAR(20) NULL,
  PRIMARY KEY (`employee_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `absences` (
  `absence_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `absence_type` VARCHAR(60) NULL,
  `start_date` DATE NULL,
  `end_date` DATE NULL,
  `status` VARCHAR(30) NULL,
  `restricted_detail_ref` VARCHAR(150) NULL,
  PRIMARY KEY (`absence_id`),
  CONSTRAINT `fk_absences_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `access_audit_logs` (
  `log_id` VARCHAR(14) NOT NULL,
  `actor_employee_id` VARCHAR(12) NULL,
  `action_type` VARCHAR(40) NULL,
  `resource_type` VARCHAR(40) NULL,
  `resource_id` VARCHAR(30) NULL,
  `access_result` VARCHAR(25) NULL,
  `created_at` DATETIME NULL,
  PRIMARY KEY (`log_id`),
  CONSTRAINT `fk_access_audit_logs_actor_employee_id` FOREIGN KEY (`actor_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `asset_registry` (
  `asset_id` VARCHAR(14) NOT NULL,
  `asset_name` VARCHAR(100) NULL,
  `asset_type` VARCHAR(45) NULL,
  `serial_number` VARCHAR(40) NULL,
  `owner_dept_id` VARCHAR(12) NULL,
  `location` VARCHAR(80) NULL,
  `status` VARCHAR(25) NULL,
  PRIMARY KEY (`asset_id`),
  UNIQUE KEY `uq_asset_registry_1_0` (`serial_number`),
  CONSTRAINT `fk_asset_registry_owner_dept_id` FOREIGN KEY (`owner_dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `attendance_records` (
  `attendance_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `work_date` DATE NULL,
  `scheduled_hours` DECIMAL(4,1) NULL,
  `worked_hours` DECIMAL(4,1) NULL,
  `attendance_status` VARCHAR(25) NULL,
  PRIMARY KEY (`attendance_id`),
  UNIQUE KEY `uq_attendance_records_2_0` (`employee_id`, `work_date`),
  CONSTRAINT `fk_attendance_records_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `chat_sessions` (
  `session_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `started_at` DATETIME NULL,
  `ended_at` DATETIME NULL,
  `channel` VARCHAR(30) NULL,
  `auth_level` VARCHAR(40) NULL,
  PRIMARY KEY (`session_id`),
  CONSTRAINT `fk_chat_sessions_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `compliance_cases` (
  `case_id` VARCHAR(14) NOT NULL,
  `case_type` VARCHAR(60) NULL,
  `received_at` DATETIME NULL,
  `owner_dept_id` VARCHAR(12) NULL,
  `case_status` VARCHAR(30) NULL,
  `restricted_detail_ref` VARCHAR(150) NULL,
  PRIMARY KEY (`case_id`),
  CONSTRAINT `fk_compliance_cases_owner_dept_id` FOREIGN KEY (`owner_dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `duty_delegations` (
  `delegation_id` VARCHAR(14) NOT NULL,
  `original_employee_id` VARCHAR(12) NULL,
  `substitute_employee_id` VARCHAR(12) NULL,
  `start_date` DATE NULL,
  `end_date` DATE NULL,
  `reason` VARCHAR(160) NULL,
  PRIMARY KEY (`delegation_id`),
  CONSTRAINT `fk_duty_delegations_original_employee_id` FOREIGN KEY (`original_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_duty_delegations_substitute_employee_id` FOREIGN KEY (`substitute_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `employee_assignments` (
  `assignment_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `dept_id` VARCHAR(12) NULL,
  `position_title` VARCHAR(60) NULL,
  `start_date` DATE NULL,
  `end_date` DATE NULL,
  `is_primary` TINYINT NULL,
  PRIMARY KEY (`assignment_id`),
  CONSTRAINT `fk_employee_assignments_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_employee_assignments_dept_id` FOREIGN KEY (`dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `employee_contacts` (
  `employee_id` VARCHAR(12) NOT NULL,
  `work_email` VARCHAR(130) NULL,
  `extension_number` VARCHAR(12) NULL,
  `work_location` VARCHAR(100) NULL,
  `contact_visibility` VARCHAR(25) NULL,
  `photo_path` VARCHAR(260) NULL,
  `photo_url` VARCHAR(500) NULL,
  `photo_status` VARCHAR(30) NULL,
  `photo_source` VARCHAR(40) NULL,
  `photo_alt` VARCHAR(150) NULL,
  PRIMARY KEY (`employee_id`),
  UNIQUE KEY `uq_employee_contacts_1_0` (`work_email`),
  CONSTRAINT `fk_employee_contacts_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `employee_roles` (
  `employee_role_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `role_id` VARCHAR(12) NULL,
  `start_date` DATE NULL,
  `end_date` DATE NULL,
  PRIMARY KEY (`employee_role_id`),
  CONSTRAINT `fk_employee_roles_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_employee_roles_role_id` FOREIGN KEY (`role_id`) REFERENCES `duty_roles` (`role_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `expense_claims` (
  `claim_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `expense_type` VARCHAR(35) NULL,
  `amount` INT NULL,
  `currency` VARCHAR(5) NULL,
  `receipt_ref` VARCHAR(180) NULL,
  `approval_status` VARCHAR(25) NULL,
  PRIMARY KEY (`claim_id`),
  CONSTRAINT `fk_expense_claims_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_adjustments` (
  `adjustment_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `year` INT NULL,
  `adjustment_days` DECIMAL(5,2) NULL,
  `reason` VARCHAR(160) NULL,
  `approved_by` VARCHAR(12) NULL,
  `created_at` DATETIME NULL,
  PRIMARY KEY (`adjustment_id`),
  CONSTRAINT `fk_leave_adjustments_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_leave_adjustments_approved_by` FOREIGN KEY (`approved_by`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_balances` (
  `balance_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `year` INT NULL,
  `granted_days` DECIMAL(5,2) NULL,
  `carryover_days` DECIMAL(5,2) NULL,
  `adjusted_days` DECIMAL(5,2) NULL,
  `updated_at` DATETIME NULL,
  PRIMARY KEY (`balance_id`),
  UNIQUE KEY `uq_leave_balances_2_0` (`employee_id`, `year`),
  CONSTRAINT `fk_leave_balances_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `payroll_monthly` (
  `payroll_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `pay_month` CHAR(7) NULL,
  `base_pay` INT NULL,
  `allowance_total` INT NULL,
  `deduction_total` INT NULL,
  `net_pay` INT NULL,
  PRIMARY KEY (`payroll_id`),
  UNIQUE KEY `uq_payroll_monthly_2_0` (`employee_id`, `pay_month`),
  CONSTRAINT `fk_payroll_monthly_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `performance_reviews` (
  `review_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `review_year` INT NULL,
  `review_type` VARCHAR(40) NULL,
  `result_code` VARCHAR(20) NULL,
  `visibility` VARCHAR(30) NULL,
  PRIMARY KEY (`review_id`),
  UNIQUE KEY `uq_performance_reviews_3_0` (`employee_id`, `review_year`, `review_type`),
  CONSTRAINT `fk_performance_reviews_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `personnel_actions` (
  `action_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `action_type` VARCHAR(35) NULL,
  `from_dept_id` VARCHAR(12) NULL,
  `to_dept_id` VARCHAR(12) NULL,
  `effective_date` DATE NULL,
  PRIMARY KEY (`action_id`),
  CONSTRAINT `fk_personnel_actions_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_personnel_actions_from_dept_id` FOREIGN KEY (`from_dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_personnel_actions_to_dept_id` FOREIGN KEY (`to_dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `procurement_contracts` (
  `contract_id` VARCHAR(14) NOT NULL,
  `contract_type` VARCHAR(45) NULL,
  `owner_dept_id` VARCHAR(12) NULL,
  `vendor_alias` VARCHAR(90) NULL,
  `contract_amount` BIGINT NULL,
  `start_date` DATE NULL,
  `end_date` DATE NULL,
  `status` VARCHAR(25) NULL,
  PRIMARY KEY (`contract_id`),
  CONSTRAINT `fk_procurement_contracts_owner_dept_id` FOREIGN KEY (`owner_dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `rd_projects` (
  `project_id` VARCHAR(14) NOT NULL,
  `project_name` VARCHAR(150) NULL,
  `lead_employee_id` VARCHAR(12) NULL,
  `owner_dept_id` VARCHAR(12) NULL,
  `budget` BIGINT NULL,
  `start_date` DATE NULL,
  `end_date` DATE NULL,
  `status` VARCHAR(30) NULL,
  PRIMARY KEY (`project_id`),
  CONSTRAINT `fk_rd_projects_lead_employee_id` FOREIGN KEY (`lead_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_rd_projects_owner_dept_id` FOREIGN KEY (`owner_dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `regulations` (
  `regulation_id` VARCHAR(12) NOT NULL,
  `title` VARCHAR(200) NULL,
  `category` VARCHAR(40) NULL,
  `regulation_type` VARCHAR(30) NULL,
  `owner_dept_id` VARCHAR(12) NULL,
  `access_level` VARCHAR(25) NULL,
  PRIMARY KEY (`regulation_id`),
  CONSTRAINT `fk_regulations_owner_dept_id` FOREIGN KEY (`owner_dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `safety_incidents` (
  `incident_id` VARCHAR(14) NOT NULL,
  `reported_at` DATETIME NULL,
  `location` VARCHAR(100) NULL,
  `incident_type` VARCHAR(70) NULL,
  `severity` VARCHAR(20) NULL,
  `owner_employee_id` VARCHAR(12) NULL,
  `status` VARCHAR(30) NULL,
  PRIMARY KEY (`incident_id`),
  CONSTRAINT `fk_safety_incidents_owner_employee_id` FOREIGN KEY (`owner_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `topic_keywords` (
  `keyword_id` VARCHAR(14) NOT NULL,
  `topic_id` VARCHAR(12) NULL,
  `keyword` VARCHAR(100) NULL,
  `synonym` VARCHAR(100) NULL,
  `match_weight` DECIMAL(4,2) NULL,
  PRIMARY KEY (`keyword_id`),
  CONSTRAINT `fk_topic_keywords_topic_id` FOREIGN KEY (`topic_id`) REFERENCES `business_topics` (`topic_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `topic_ownerships` (
  `ownership_id` VARCHAR(14) NOT NULL,
  `topic_id` VARCHAR(12) NULL,
  `dept_id` VARCHAR(12) NULL,
  `primary_employee_id` VARCHAR(12) NULL,
  `backup_employee_id` VARCHAR(12) NULL,
  `approver_employee_id` VARCHAR(12) NULL,
  `priority` TINYINT NULL,
  `effective_from` DATE NULL,
  `effective_to` DATE NULL,
  PRIMARY KEY (`ownership_id`),
  CONSTRAINT `fk_topic_ownerships_topic_id` FOREIGN KEY (`topic_id`) REFERENCES `business_topics` (`topic_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_topic_ownerships_dept_id` FOREIGN KEY (`dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_topic_ownerships_primary_employee_id` FOREIGN KEY (`primary_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_topic_ownerships_backup_employee_id` FOREIGN KEY (`backup_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_topic_ownerships_approver_employee_id` FOREIGN KEY (`approver_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `training_history` (
  `training_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `course_name` VARCHAR(100) NULL,
  `provider` VARCHAR(80) NULL,
  `start_date` DATE NULL,
  `end_date` DATE NULL,
  `completion_status` VARCHAR(25) NULL,
  PRIMARY KEY (`training_id`),
  CONSTRAINT `fk_training_history_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `travel_requests` (
  `travel_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `travel_type` VARCHAR(30) NULL,
  `destination` VARCHAR(100) NULL,
  `start_date` DATE NULL,
  `end_date` DATE NULL,
  `approval_status` VARCHAR(25) NULL,
  PRIMARY KEY (`travel_id`),
  CONSTRAINT `fk_travel_requests_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `asset_assignments` (
  `assignment_id` VARCHAR(14) NOT NULL,
  `asset_id` VARCHAR(14) NULL,
  `employee_id` VARCHAR(12) NULL,
  `issued_at` DATE NULL,
  `returned_at` DATE NULL,
  `status` VARCHAR(25) NULL,
  PRIMARY KEY (`assignment_id`),
  CONSTRAINT `fk_asset_assignments_asset_id` FOREIGN KEY (`asset_id`) REFERENCES `asset_registry` (`asset_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_asset_assignments_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `benefit_programs` (
  `benefit_id` VARCHAR(14) NOT NULL,
  `benefit_name` VARCHAR(120) NULL,
  `eligibility_rule` VARCHAR(250) NULL,
  `annual_limit` INT NULL,
  `owner_topic_id` VARCHAR(12) NULL,
  `regulation_id` VARCHAR(12) NULL,
  PRIMARY KEY (`benefit_id`),
  CONSTRAINT `fk_benefit_programs_owner_topic_id` FOREIGN KEY (`owner_topic_id`) REFERENCES `business_topics` (`topic_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_benefit_programs_regulation_id` FOREIGN KEY (`regulation_id`) REFERENCES `regulations` (`regulation_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `chat_messages` (
  `message_id` VARCHAR(14) NOT NULL,
  `session_id` VARCHAR(14) NULL,
  `sender_role` VARCHAR(20) NULL,
  `message_text` TEXT NULL,
  `created_at` DATETIME NULL,
  PRIMARY KEY (`message_id`),
  CONSTRAINT `fk_chat_messages_session_id` FOREIGN KEY (`session_id`) REFERENCES `chat_sessions` (`session_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ip_records` (
  `ip_id` VARCHAR(14) NOT NULL,
  `project_id` VARCHAR(14) NULL,
  `ip_type` VARCHAR(45) NULL,
  `ip_title` VARCHAR(150) NULL,
  `filing_number` VARCHAR(50) NULL,
  `status` VARCHAR(30) NULL,
  PRIMARY KEY (`ip_id`),
  CONSTRAINT `fk_ip_records_project_id` FOREIGN KEY (`project_id`) REFERENCES `rd_projects` (`project_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `regulation_versions` (
  `version_id` VARCHAR(14) NOT NULL,
  `regulation_id` VARCHAR(12) NULL,
  `revision_number` VARCHAR(20) NULL,
  `revision_date` DATE NULL,
  `revision_label` VARCHAR(100) NULL,
  `effective_date` DATE NULL,
  `file_path` VARCHAR(400) NULL,
  `file_hash` VARCHAR(64) NULL,
  `status` VARCHAR(35) NULL,
  `page_count` INT NULL,
  PRIMARY KEY (`version_id`),
  CONSTRAINT `fk_regulation_versions_regulation_id` FOREIGN KEY (`regulation_id`) REFERENCES `regulations` (`regulation_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `routing_logs` (
  `routing_id` VARCHAR(14) NOT NULL,
  `session_id` VARCHAR(14) NULL,
  `topic_id` VARCHAR(12) NULL,
  `confidence_score` DECIMAL(4,3) NULL,
  `selected_dept_id` VARCHAR(12) NULL,
  `assigned_employee_id` VARCHAR(12) NULL,
  `routing_status` VARCHAR(30) NULL,
  `routed_at` DATETIME NULL,
  PRIMARY KEY (`routing_id`),
  CONSTRAINT `fk_routing_logs_session_id` FOREIGN KEY (`session_id`) REFERENCES `chat_sessions` (`session_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_routing_logs_topic_id` FOREIGN KEY (`topic_id`) REFERENCES `business_topics` (`topic_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_routing_logs_selected_dept_id` FOREIGN KEY (`selected_dept_id`) REFERENCES `departments` (`dept_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_routing_logs_assigned_employee_id` FOREIGN KEY (`assigned_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `support_tickets` (
  `ticket_id` VARCHAR(14) NOT NULL,
  `session_id` VARCHAR(14) NULL,
  `employee_id` VARCHAR(12) NULL,
  `topic_id` VARCHAR(12) NULL,
  `owner_employee_id` VARCHAR(12) NULL,
  `priority` VARCHAR(20) NULL,
  `status` VARCHAR(30) NULL,
  `created_at` DATETIME NULL,
  `closed_at` DATETIME NULL,
  PRIMARY KEY (`ticket_id`),
  CONSTRAINT `fk_support_tickets_session_id` FOREIGN KEY (`session_id`) REFERENCES `chat_sessions` (`session_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_support_tickets_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_support_tickets_topic_id` FOREIGN KEY (`topic_id`) REFERENCES `business_topics` (`topic_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_support_tickets_owner_employee_id` FOREIGN KEY (`owner_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `benefit_applications` (
  `application_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `benefit_id` VARCHAR(14) NULL,
  `requested_amount` INT NULL,
  `application_date` DATE NULL,
  `status` VARCHAR(25) NULL,
  PRIMARY KEY (`application_id`),
  CONSTRAINT `fk_benefit_applications_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_benefit_applications_benefit_id` FOREIGN KEY (`benefit_id`) REFERENCES `benefit_programs` (`benefit_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `regulation_articles` (
  `article_id` VARCHAR(18) NOT NULL,
  `version_id` VARCHAR(14) NULL,
  `chapter_number` VARCHAR(20) NULL,
  `article_number` VARCHAR(35) NULL,
  `article_title` VARCHAR(200) NULL,
  `article_text` LONGTEXT NULL,
  `page_number` INT NULL,
  `extraction_status` VARCHAR(30) NULL,
  PRIMARY KEY (`article_id`),
  CONSTRAINT `fk_regulation_articles_version_id` FOREIGN KEY (`version_id`) REFERENCES `regulation_versions` (`version_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `satisfaction_surveys` (
  `survey_id` VARCHAR(14) NOT NULL,
  `ticket_id` VARCHAR(14) NULL,
  `score` TINYINT NULL,
  `reason_code` VARCHAR(40) NULL,
  `comment` VARCHAR(250) NULL,
  `submitted_at` DATETIME NULL,
  PRIMARY KEY (`survey_id`),
  UNIQUE KEY `uq_satisfaction_surveys_1_0` (`ticket_id`),
  CONSTRAINT `fk_satisfaction_surveys_ticket_id` FOREIGN KEY (`ticket_id`) REFERENCES `support_tickets` (`ticket_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ticket_events` (
  `event_id` VARCHAR(14) NOT NULL,
  `ticket_id` VARCHAR(14) NULL,
  `actor_employee_id` VARCHAR(12) NULL,
  `event_type` VARCHAR(35) NULL,
  `previous_status` VARCHAR(25) NULL,
  `new_status` VARCHAR(25) NULL,
  `occurred_at` DATETIME NULL,
  PRIMARY KEY (`event_id`),
  CONSTRAINT `fk_ticket_events_ticket_id` FOREIGN KEY (`ticket_id`) REFERENCES `support_tickets` (`ticket_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_ticket_events_actor_employee_id` FOREIGN KEY (`actor_employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_types` (
  `leave_type_id` VARCHAR(12) NOT NULL,
  `type_name` VARCHAR(60) NULL,
  `paid_flag` TINYINT NULL,
  `deducts_annual_leave` TINYINT NULL,
  `minimum_unit` DECIMAL(4,2) NULL,
  `regulation_article_id` VARCHAR(18) NULL,
  PRIMARY KEY (`leave_type_id`),
  CONSTRAINT `fk_leave_types_regulation_article_id` FOREIGN KEY (`regulation_article_id`) REFERENCES `regulation_articles` (`article_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `regulation_chunks` (
  `chunk_id` VARCHAR(20) NOT NULL,
  `article_id` VARCHAR(18) NULL,
  `chunk_order` INT NULL,
  `chunk_text` TEXT NULL,
  `embedding_ref` VARCHAR(200) NULL,
  `source_page` INT NULL,
  PRIMARY KEY (`chunk_id`),
  CONSTRAINT `fk_regulation_chunks_article_id` FOREIGN KEY (`article_id`) REFERENCES `regulation_articles` (`article_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `topic_regulations` (
  `topic_regulation_id` VARCHAR(14) NOT NULL,
  `topic_id` VARCHAR(12) NULL,
  `article_id` VARCHAR(18) NULL,
  `relevance_type` VARCHAR(25) NULL,
  `priority` TINYINT NULL,
  PRIMARY KEY (`topic_regulation_id`),
  UNIQUE KEY `uq_topic_regulations_2_0` (`topic_id`, `article_id`),
  CONSTRAINT `fk_topic_regulations_topic_id` FOREIGN KEY (`topic_id`) REFERENCES `business_topics` (`topic_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_topic_regulations_article_id` FOREIGN KEY (`article_id`) REFERENCES `regulation_articles` (`article_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `leave_transactions` (
  `transaction_id` VARCHAR(14) NOT NULL,
  `employee_id` VARCHAR(12) NULL,
  `leave_type_id` VARCHAR(12) NULL,
  `start_date` DATE NULL,
  `end_date` DATE NULL,
  `days` DECIMAL(5,2) NULL,
  `status` VARCHAR(25) NULL,
  `requested_at` DATETIME NULL,
  `approved_by` VARCHAR(12) NULL,
  PRIMARY KEY (`transaction_id`),
  CONSTRAINT `fk_leave_transactions_employee_id` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_leave_transactions_leave_type_id` FOREIGN KEY (`leave_type_id`) REFERENCES `leave_types` (`leave_type_id`) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_leave_transactions_approved_by` FOREIGN KEY (`approved_by`) REFERENCES `employees` (`employee_id`) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Views deliberately aggregate transactions, avoiding stored duplicate USED/APPROVED totals.
CREATE OR REPLACE VIEW `v_leave_balance` AS
SELECT e.employee_id, e.employee_name, b.`year`, b.granted_days, b.carryover_days, b.adjusted_days,
 COALESCE(SUM(CASE WHEN t.`status` = 'USED' AND lt.deducts_annual_leave=1 THEN t.days ELSE 0 END),0) AS used_days,
 COALESCE(SUM(CASE WHEN t.`status` = 'APPROVED' AND lt.deducts_annual_leave=1 THEN t.days ELSE 0 END),0) AS reserved_days,
 b.granted_days+b.carryover_days+b.adjusted_days-COALESCE(SUM(CASE WHEN t.`status` IN ('USED','APPROVED') AND lt.deducts_annual_leave=1 THEN t.days ELSE 0 END),0) AS remaining_days
FROM leave_balances b JOIN employees e ON e.employee_id=b.employee_id
LEFT JOIN leave_transactions t ON t.employee_id=b.employee_id AND YEAR(t.start_date)=b.`year`
LEFT JOIN leave_types lt ON lt.leave_type_id=t.leave_type_id
GROUP BY e.employee_id,e.employee_name,b.`year`,b.granted_days,b.carryover_days,b.adjusted_days;

CREATE OR REPLACE VIEW `v_employee_directory` AS
SELECT e.employee_id,e.employee_name,e.grade,d.dept_name,a.position_title,c.work_email,c.extension_number,c.photo_path,c.photo_url,c.photo_status
FROM employees e JOIN employee_assignments a ON a.employee_id=e.employee_id AND a.is_primary=1 AND a.end_date IS NULL
JOIN departments d ON d.dept_id=a.dept_id JOIN employee_contacts c ON c.employee_id=e.employee_id
WHERE e.employment_status='재직';

CREATE OR REPLACE VIEW `v_topic_contact_cards` AS
SELECT t.topic_id,t.topic_name,ow.dept_id,d.dept_name,ow.primary_employee_id AS employee_id,e.employee_name,c.extension_number,c.work_email,c.photo_path,c.photo_url,c.photo_status,ow.backup_employee_id
FROM business_topics t JOIN topic_ownerships ow ON ow.topic_id=t.topic_id AND ow.effective_to IS NULL
JOIN departments d ON d.dept_id=ow.dept_id JOIN employees e ON e.employee_id=ow.primary_employee_id
JOIN employee_contacts c ON c.employee_id=e.employee_id;
