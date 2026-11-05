# DB 컬럼 사전

조사 시각: 2026-11-05T19:25:15.615648+09:00

실제 DB의 PRAGMA 정보 및 참고 DDL에서 추출했습니다. 개인·대화 본문 데이터는 포함하지 않습니다.

## app

원본: `C:\Users\KDT\Desktop\KDT AI Agent\my-chatbot\data\app.sqlite3`

### conversations

행 수: 103

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | TEXT | PK | Y |  |
| employee_id | TEXT |  | Y |  |
| status | TEXT |  | Y |  |
| created_at | TEXT |  | Y |  |
| ended_at | TEXT |  | N |  |
| end_result | TEXT |  | N |  |

복합/단일 유일 인덱스: (id)

### departments

행 수: 16

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| dept_id | TEXT | PK | Y |  |
| dept_name | TEXT | UK | Y |  |
| parent_dept_id | TEXT | FK | N | departments.dept_id |
| dept_function | TEXT |  | N |  |
| location | TEXT |  | N |  |
| main_extension | TEXT |  | N |  |
| is_active | TINYINT |  | Y |  |

복합/단일 유일 인덱스: (dept_name), (dept_id)

### duty_roles

행 수: 5

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| role_id | TEXT | PK | Y |  |
| role_name | TEXT |  | Y |  |
| role_category | TEXT |  | N |  |
| description | TEXT |  | N |  |
| security_level | TEXT |  | N |  |

복합/단일 유일 인덱스: (role_id)

### employee_assignments

행 수: 100

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| assignment_id | TEXT | PK | Y |  |
| employee_id | TEXT | FK | Y | employees.employee_id |
| dept_id | TEXT | FK | Y | departments.dept_id |
| position_title | TEXT |  | Y |  |
| start_date | TEXT |  | Y |  |
| end_date | TEXT |  | N |  |
| is_primary | TINYINT |  | Y |  |

복합/단일 유일 인덱스: (assignment_id)

### employee_contacts

행 수: 100

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_id | TEXT | PK, FK | Y | employees.employee_id |
| work_email | TEXT | UK | N |  |
| extension_number | TEXT |  | N |  |
| work_location | TEXT |  | N |  |
| contact_visibility | TEXT |  | Y |  |
| photo_path | TEXT |  | N |  |
| photo_url | TEXT |  | N |  |
| photo_status | TEXT |  | Y |  |
| photo_source | TEXT |  | N |  |
| photo_alt | TEXT |  | N |  |
| source_page_url | TEXT |  | N |  |
| license_url | TEXT |  | N |  |
| fallback_photo_path | TEXT |  | N |  |
| photo_file_status | TEXT |  | Y |  |

복합/단일 유일 인덱스: (work_email), (employee_id)

### employee_roles

행 수: 100

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_role_id | TEXT | PK | Y |  |
| employee_id | TEXT | FK | Y | employees.employee_id |
| role_id | TEXT | FK | Y | duty_roles.role_id |
| start_date | TEXT |  | Y |  |
| end_date | TEXT |  | N |  |

복합/단일 유일 인덱스: (employee_role_id)

### employees

행 수: 102

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_id | TEXT | PK | Y |  |
| name | TEXT |  | Y |  |
| department | TEXT |  | N |  |
| job_title | TEXT |  | N |  |
| hired_at | TEXT |  | N |  |
| grade | TEXT |  | N |  |
| employment_type | TEXT |  | N |  |
| employment_status | TEXT |  | N |  |
| created_at | TEXT |  | Y |  |

복합/단일 유일 인덱스: (employee_id)

### feedback

행 수: 8

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | INTEGER | PK | Y |  |
| conversation_id | TEXT | FK, UK | Y | conversations.id |
| rating | TEXT |  | N |  |
| comment | TEXT |  | N |  |
| created_at | TEXT |  | Y |  |

복합/단일 유일 인덱스: (conversation_id)

### leave_balances

행 수: 0

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_id | TEXT | PK, FK | Y | employees.employee_id |
| balance_year | SMALLINT | PK | Y |  |
| granted_days | DECIMAL(6,2) |  | Y |  |
| used_days | DECIMAL(6,2) |  | Y |  |
| updated_at | TEXT |  | Y |  |

복합/단일 유일 인덱스: (employee_id, balance_year)

### messages

행 수: 304

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| sequence_id | INTEGER | PK | Y |  |
| id | TEXT | UK | Y |  |
| conversation_id | TEXT | FK | Y | conversations.id |
| role | TEXT |  | Y |  |
| content | TEXT |  | Y |  |
| sources | TEXT |  | N |  |
| tools_used | TEXT |  | N |  |
| context_data | TEXT |  | N |  |
| created_at | TEXT |  | Y |  |

복합/단일 유일 인덱스: (id)

### policy_documents

행 수: 0

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | TEXT | PK | Y |  |
| domain | TEXT |  | Y |  |
| filename | TEXT |  | Y |  |
| version | TEXT |  | N |  |
| effective_date | TEXT |  | N |  |
| file_path | TEXT |  | Y |  |
| created_at | TEXT |  | Y |  |

복합/단일 유일 인덱스: (id)

### webhook_events

행 수: 8

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| event_id | TEXT | PK | Y |  |
| conversation_id | TEXT | FK, UK | Y | conversations.id |
| event_type | TEXT |  | Y |  |
| payload | TEXT |  | Y |  |
| status | TEXT |  | Y |  |
| attempts | INT |  | Y |  |
| last_error | TEXT |  | N |  |
| created_at | TEXT |  | Y |  |
| sent_at | TEXT |  | N |  |

복합/단일 유일 인덱스: (conversation_id), (event_id)

### VIEW: v_employee_profiles

참조: departments, employee_assignments, employee_contacts, employees

## directory

원본: `C:\Users\KDT\Desktop\KDT AI Agent\my-chatbot\database\employee_directory\employee_directory.sqlite3`

### departments

행 수: 16

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| dept_id | TEXT | PK | Y |  |
| dept_name | TEXT | UK | Y |  |
| parent_dept_id | TEXT | FK | N | departments.dept_id |
| dept_function | TEXT |  | N |  |
| location | TEXT |  | N |  |
| main_extension | TEXT |  | N |  |
| is_active | TINYINT |  | Y |  |

복합/단일 유일 인덱스: (dept_name), (dept_id)

### duty_roles

행 수: 5

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| role_id | TEXT | PK | Y |  |
| role_name | TEXT |  | Y |  |
| role_category | TEXT |  | N |  |
| description | TEXT |  | N |  |
| security_level | TEXT |  | N |  |

복합/단일 유일 인덱스: (role_id)

### employee_assignments

행 수: 100

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| assignment_id | TEXT | PK | Y |  |
| employee_id | TEXT | FK | Y | employees.employee_id |
| dept_id | TEXT | FK | Y | departments.dept_id |
| position_title | TEXT |  | Y |  |
| start_date | TEXT |  | Y |  |
| end_date | TEXT |  | N |  |
| is_primary | TINYINT |  | Y |  |

복합/단일 유일 인덱스: (assignment_id)

### employee_contacts

행 수: 100

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_id | TEXT | PK, FK | Y | employees.employee_id |
| work_email | TEXT | UK | N |  |
| extension_number | TEXT |  | N |  |
| work_location | TEXT |  | N |  |
| contact_visibility | TEXT |  | Y |  |
| photo_path | TEXT |  | N |  |
| photo_url | TEXT |  | N |  |
| photo_status | TEXT |  | Y |  |
| photo_source | TEXT |  | N |  |
| photo_alt | TEXT |  | N |  |
| source_page_url | TEXT |  | N |  |
| license_url | TEXT |  | N |  |
| fallback_photo_path | TEXT |  | N |  |
| photo_file_status | TEXT |  | Y |  |

복합/단일 유일 인덱스: (work_email), (employee_id)

### employee_roles

행 수: 100

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_role_id | TEXT | PK | Y |  |
| employee_id | TEXT | FK | Y | employees.employee_id |
| role_id | TEXT | FK | Y | duty_roles.role_id |
| start_date | TEXT |  | Y |  |
| end_date | TEXT |  | N |  |

복합/단일 유일 인덱스: (employee_role_id)

### employees

행 수: 100

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_id | TEXT | PK | Y |  |
| name | TEXT |  | Y |  |
| department | TEXT |  | N |  |
| job_title | TEXT |  | N |  |
| hired_at | TEXT |  | N |  |
| grade | TEXT |  | N |  |
| employment_type | TEXT |  | N |  |
| employment_status | TEXT |  | N |  |
| created_at | TEXT |  | Y |  |

복합/단일 유일 인덱스: (employee_id)

### VIEW: v_employee_profiles

참조: departments, employee_assignments, employee_contacts, employees

## chroma_active

원본: `C:\Users\KDT\Desktop\KDT AI Agent\kdn_regulations_rag\rag_data\chroma_db\chroma.sqlite3`

### acquire_write

행 수: 95

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | INTEGER | PK | Y |  |
| lock_status | INTEGER |  | Y |  |

복합/단일 유일 인덱스: 없음

### collection_metadata

행 수: 4

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| collection_id | TEXT | PK, FK | Y | collections.id |
| key | TEXT | PK | Y |  |
| str_value | TEXT |  | N |  |
| int_value | INTEGER |  | N |  |
| float_value | REAL |  | N |  |
| bool_value | INTEGER |  | N |  |

복합/단일 유일 인덱스: (collection_id, key)

### collections

행 수: 1

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | TEXT | PK | Y |  |
| name | TEXT |  | Y |  |
| dimension | INTEGER |  | N |  |
| database_id | TEXT | FK | Y | databases.id |
| config_json_str | TEXT |  | N |  |
| schema_str | TEXT |  | N |  |

복합/단일 유일 인덱스: (name, database_id), (id)

### databases

행 수: 1

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | TEXT | PK | Y |  |
| name | TEXT |  | Y |  |
| tenant_id | TEXT | FK | Y | tenants.id |

복합/단일 유일 인덱스: (tenant_id, name), (id)

### embedding_fulltext_search

행 수: 7117

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| string_value | untyped |  | N |  |

복합/단일 유일 인덱스: 없음

### embedding_fulltext_search_config

행 수: 1

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| k | untyped | PK | Y |  |
| v | untyped |  | N |  |

복합/단일 유일 인덱스: (k)

### embedding_fulltext_search_content

행 수: 7117

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | INTEGER | PK | Y |  |
| c0 | untyped |  | N |  |

복합/단일 유일 인덱스: 없음

### embedding_fulltext_search_data

행 수: 1418

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | INTEGER | PK | Y |  |
| block | BLOB |  | N |  |

복합/단일 유일 인덱스: 없음

### embedding_fulltext_search_docsize

행 수: 7117

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | INTEGER | PK | Y |  |
| sz | BLOB |  | N |  |

복합/단일 유일 인덱스: 없음

### embedding_fulltext_search_idx

행 수: 1375

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| segid | untyped | PK | Y |  |
| term | untyped | PK | Y |  |
| pgno | untyped |  | N |  |

복합/단일 유일 인덱스: (segid, term)

### embedding_metadata

행 수: 92521

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | INTEGER | PK, FK | Y | embeddings.id |
| key | TEXT | PK | Y |  |
| string_value | TEXT |  | N |  |
| int_value | INTEGER |  | N |  |
| float_value | REAL |  | N |  |
| bool_value | INTEGER |  | N |  |

복합/단일 유일 인덱스: (id, key)

### embedding_metadata_array

행 수: 0

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | INTEGER | FK | Y | embeddings.id |
| key | TEXT |  | Y |  |
| string_value | TEXT |  | N |  |
| int_value | INTEGER |  | N |  |
| float_value | REAL |  | N |  |
| bool_value | INTEGER |  | N |  |

복합/단일 유일 인덱스: 없음

### embeddings

행 수: 7117

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | INTEGER | PK | Y |  |
| segment_id | TEXT |  | Y |  |
| embedding_id | TEXT |  | Y |  |
| seq_id | BLOB |  | Y |  |
| created_at | TIMESTAMP |  | Y |  |

복합/단일 유일 인덱스: (segment_id, embedding_id)

### embeddings_queue

행 수: 505

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| seq_id | INTEGER | PK | Y |  |
| created_at | TIMESTAMP |  | Y |  |
| operation | INTEGER |  | Y |  |
| topic | TEXT |  | Y |  |
| id | TEXT |  | Y |  |
| vector | BLOB |  | N |  |
| encoding | TEXT |  | N |  |
| metadata | TEXT |  | N |  |

복합/단일 유일 인덱스: 없음

### embeddings_queue_config

행 수: 1

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | INTEGER | PK | Y |  |
| config_json_str | TEXT |  | N |  |

복합/단일 유일 인덱스: 없음

### maintenance_log

행 수: 0

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | INT | PK | Y |  |
| timestamp | INT |  | Y |  |
| operation | TEXT |  | Y |  |

복합/단일 유일 인덱스: (id)

### max_seq_id

행 수: 2

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| segment_id | TEXT | PK | Y |  |
| seq_id | INTEGER |  | N |  |

복합/단일 유일 인덱스: (segment_id)

### migrations

행 수: 18

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| dir | TEXT | PK | Y |  |
| version | INTEGER | PK | Y |  |
| filename | TEXT |  | Y |  |
| sql | TEXT |  | Y |  |
| hash | TEXT |  | Y |  |

복합/단일 유일 인덱스: (dir, version)

### segment_metadata

행 수: 0

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| segment_id | TEXT | PK, FK | Y | segments.id |
| key | TEXT | PK | Y |  |
| str_value | TEXT |  | N |  |
| int_value | INTEGER |  | N |  |
| float_value | REAL |  | N |  |
| bool_value | INTEGER |  | N |  |

복합/단일 유일 인덱스: (segment_id, key)

### segments

행 수: 2

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | TEXT | PK | Y |  |
| type | TEXT |  | Y |  |
| scope | TEXT |  | Y |  |
| collection | TEXT | FK | Y | collection.id |

복합/단일 유일 인덱스: (id)

### tenants

행 수: 1

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| id | TEXT | PK | Y |  |

복합/단일 유일 인덱스: (id)

## enterprise_reference

원본: `C:\Users\KDT\Desktop\KDT AI Agent\data\KDN_Enterprise_AI_Dataset\KDN_Enterprise_AI_Dataset_Pexels\sql\01_create_schema.sql`

### absences

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| absence_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| absence_type | VARCHAR(60) |  | N |  |
| start_date | DATE |  | N |  |
| end_date | DATE |  | N |  |
| status | VARCHAR(30) |  | N |  |
| restricted_detail_ref | VARCHAR(150) |  | N |  |

복합/단일 유일 인덱스: (absence_id)

### access_audit_logs

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| log_id | VARCHAR(14) | PK | Y |  |
| actor_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| action_type | VARCHAR(40) |  | N |  |
| resource_type | VARCHAR(40) |  | N |  |
| resource_id | VARCHAR(30) |  | N |  |
| access_result | VARCHAR(25) |  | N |  |
| created_at | DATETIME |  | N |  |

복합/단일 유일 인덱스: (log_id)

### asset_assignments

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| assignment_id | VARCHAR(14) | PK | Y |  |
| asset_id | VARCHAR(14) | FK | N | asset_registry.asset_id |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| issued_at | DATE |  | N |  |
| returned_at | DATE |  | N |  |
| status | VARCHAR(25) |  | N |  |

복합/단일 유일 인덱스: (assignment_id)

### asset_registry

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| asset_id | VARCHAR(14) | PK | Y |  |
| asset_name | VARCHAR(100) |  | N |  |
| asset_type | VARCHAR(45) |  | N |  |
| serial_number | VARCHAR(40) | UK | N |  |
| owner_dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| location | VARCHAR(80) |  | N |  |
| status | VARCHAR(25) |  | N |  |

복합/단일 유일 인덱스: (serial_number), (asset_id)

### attendance_records

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| attendance_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| work_date | DATE |  | N |  |
| scheduled_hours | DECIMAL(4,1) |  | N |  |
| worked_hours | DECIMAL(4,1) |  | N |  |
| attendance_status | VARCHAR(25) |  | N |  |

복합/단일 유일 인덱스: (employee_id, work_date), (attendance_id)

### benefit_applications

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| application_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| benefit_id | VARCHAR(14) | FK | N | benefit_programs.benefit_id |
| requested_amount | INT |  | N |  |
| application_date | DATE |  | N |  |
| status | VARCHAR(25) |  | N |  |

복합/단일 유일 인덱스: (application_id)

### benefit_programs

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| benefit_id | VARCHAR(14) | PK | Y |  |
| benefit_name | VARCHAR(120) |  | N |  |
| eligibility_rule | VARCHAR(250) |  | N |  |
| annual_limit | INT |  | N |  |
| owner_topic_id | VARCHAR(12) | FK | N | business_topics.topic_id |
| regulation_id | VARCHAR(12) | FK | N | regulations.regulation_id |

복합/단일 유일 인덱스: (benefit_id)

### business_topics

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| topic_id | VARCHAR(12) | PK | Y |  |
| topic_name | VARCHAR(200) |  | N |  |
| category | VARCHAR(40) |  | N |  |
| description | TEXT |  | N |  |
| intent_type | VARCHAR(30) |  | N |  |
| security_level | VARCHAR(25) |  | N |  |
| auto_answer_allowed | TINYINT |  | N |  |

복합/단일 유일 인덱스: (topic_id)

### chat_messages

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| message_id | VARCHAR(14) | PK | Y |  |
| session_id | VARCHAR(14) | FK | N | chat_sessions.session_id |
| sender_role | VARCHAR(20) |  | N |  |
| message_text | TEXT |  | N |  |
| created_at | DATETIME |  | N |  |

복합/단일 유일 인덱스: (message_id)

### chat_sessions

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| session_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| started_at | DATETIME |  | N |  |
| ended_at | DATETIME |  | N |  |
| channel | VARCHAR(30) |  | N |  |
| auth_level | VARCHAR(40) |  | N |  |

복합/단일 유일 인덱스: (session_id)

### compliance_cases

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| case_id | VARCHAR(14) | PK | Y |  |
| case_type | VARCHAR(60) |  | N |  |
| received_at | DATETIME |  | N |  |
| owner_dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| case_status | VARCHAR(30) |  | N |  |
| restricted_detail_ref | VARCHAR(150) |  | N |  |

복합/단일 유일 인덱스: (case_id)

### departments

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| dept_id | VARCHAR(12) | PK | Y |  |
| dept_name | VARCHAR(80) | UK | N |  |
| parent_dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| dept_function | VARCHAR(200) |  | N |  |
| location | VARCHAR(80) |  | N |  |
| main_extension | VARCHAR(12) |  | N |  |
| is_active | TINYINT |  | N |  |

복합/단일 유일 인덱스: (dept_name), (dept_id)

### duty_delegations

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| delegation_id | VARCHAR(14) | PK | Y |  |
| original_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| substitute_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| start_date | DATE |  | N |  |
| end_date | DATE |  | N |  |
| reason | VARCHAR(160) |  | N |  |

복합/단일 유일 인덱스: (delegation_id)

### duty_roles

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| role_id | VARCHAR(12) | PK | Y |  |
| role_name | VARCHAR(60) |  | N |  |
| role_category | VARCHAR(30) |  | N |  |
| description | VARCHAR(250) |  | N |  |
| security_level | VARCHAR(20) |  | N |  |

복합/단일 유일 인덱스: (role_id)

### employee_assignments

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| assignment_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| position_title | VARCHAR(60) |  | N |  |
| start_date | DATE |  | N |  |
| end_date | DATE |  | N |  |
| is_primary | TINYINT |  | N |  |

복합/단일 유일 인덱스: (assignment_id)

### employee_contacts

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_id | VARCHAR(12) | PK, FK | Y | employees.employee_id |
| work_email | VARCHAR(130) | UK | N |  |
| extension_number | VARCHAR(12) |  | N |  |
| work_location | VARCHAR(100) |  | N |  |
| contact_visibility | VARCHAR(25) |  | N |  |
| photo_path | VARCHAR(260) |  | N |  |
| photo_url | VARCHAR(500) |  | N |  |
| photo_status | VARCHAR(30) |  | N |  |
| photo_source | VARCHAR(40) |  | N |  |
| photo_alt | VARCHAR(150) |  | N |  |

복합/단일 유일 인덱스: (work_email), (employee_id)

### employee_roles

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_role_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| role_id | VARCHAR(12) | FK | N | duty_roles.role_id |
| start_date | DATE |  | N |  |
| end_date | DATE |  | N |  |

복합/단일 유일 인덱스: (employee_role_id)

### employees

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_id | VARCHAR(12) | PK | Y |  |
| employee_name | VARCHAR(40) |  | N |  |
| grade | VARCHAR(25) |  | N |  |
| hire_date | DATE |  | N |  |
| employment_type | VARCHAR(30) |  | N |  |
| employment_status | VARCHAR(20) |  | N |  |

복합/단일 유일 인덱스: (employee_id)

### expense_claims

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| claim_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| expense_type | VARCHAR(35) |  | N |  |
| amount | INT |  | N |  |
| currency | VARCHAR(5) |  | N |  |
| receipt_ref | VARCHAR(180) |  | N |  |
| approval_status | VARCHAR(25) |  | N |  |

복합/단일 유일 인덱스: (claim_id)

### ip_records

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| ip_id | VARCHAR(14) | PK | Y |  |
| project_id | VARCHAR(14) | FK | N | rd_projects.project_id |
| ip_type | VARCHAR(45) |  | N |  |
| ip_title | VARCHAR(150) |  | N |  |
| filing_number | VARCHAR(50) |  | N |  |
| status | VARCHAR(30) |  | N |  |

복합/단일 유일 인덱스: (ip_id)

### leave_adjustments

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| adjustment_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| year | INT |  | N |  |
| adjustment_days | DECIMAL(5,2) |  | N |  |
| reason | VARCHAR(160) |  | N |  |
| approved_by | VARCHAR(12) | FK | N | employees.employee_id |
| created_at | DATETIME |  | N |  |

복합/단일 유일 인덱스: (adjustment_id)

### leave_balances

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| balance_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| year | INT |  | N |  |
| granted_days | DECIMAL(5,2) |  | N |  |
| carryover_days | DECIMAL(5,2) |  | N |  |
| adjusted_days | DECIMAL(5,2) |  | N |  |
| updated_at | DATETIME |  | N |  |

복합/단일 유일 인덱스: (employee_id, year), (balance_id)

### leave_transactions

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| transaction_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| leave_type_id | VARCHAR(12) | FK | N | leave_types.leave_type_id |
| start_date | DATE |  | N |  |
| end_date | DATE |  | N |  |
| days | DECIMAL(5,2) |  | N |  |
| status | VARCHAR(25) |  | N |  |
| requested_at | DATETIME |  | N |  |
| approved_by | VARCHAR(12) | FK | N | employees.employee_id |

복합/단일 유일 인덱스: (transaction_id)

### leave_types

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| leave_type_id | VARCHAR(12) | PK | Y |  |
| type_name | VARCHAR(60) |  | N |  |
| paid_flag | TINYINT |  | N |  |
| deducts_annual_leave | TINYINT |  | N |  |
| minimum_unit | DECIMAL(4,2) |  | N |  |
| regulation_article_id | VARCHAR(18) | FK | N | regulation_articles.article_id |

복합/단일 유일 인덱스: (leave_type_id)

### payroll_monthly

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| payroll_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| pay_month | CHAR(7) |  | N |  |
| base_pay | INT |  | N |  |
| allowance_total | INT |  | N |  |
| deduction_total | INT |  | N |  |
| net_pay | INT |  | N |  |

복합/단일 유일 인덱스: (employee_id, pay_month), (payroll_id)

### performance_reviews

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| review_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| review_year | INT |  | N |  |
| review_type | VARCHAR(40) |  | N |  |
| result_code | VARCHAR(20) |  | N |  |
| visibility | VARCHAR(30) |  | N |  |

복합/단일 유일 인덱스: (employee_id, review_year, review_type), (review_id)

### personnel_actions

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| action_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| action_type | VARCHAR(35) |  | N |  |
| from_dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| to_dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| effective_date | DATE |  | N |  |

복합/단일 유일 인덱스: (action_id)

### procurement_contracts

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| contract_id | VARCHAR(14) | PK | Y |  |
| contract_type | VARCHAR(45) |  | N |  |
| owner_dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| vendor_alias | VARCHAR(90) |  | N |  |
| contract_amount | BIGINT |  | N |  |
| start_date | DATE |  | N |  |
| end_date | DATE |  | N |  |
| status | VARCHAR(25) |  | N |  |

복합/단일 유일 인덱스: (contract_id)

### rd_projects

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| project_id | VARCHAR(14) | PK | Y |  |
| project_name | VARCHAR(150) |  | N |  |
| lead_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| owner_dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| budget | BIGINT |  | N |  |
| start_date | DATE |  | N |  |
| end_date | DATE |  | N |  |
| status | VARCHAR(30) |  | N |  |

복합/단일 유일 인덱스: (project_id)

### regulation_articles

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| article_id | VARCHAR(18) | PK | Y |  |
| version_id | VARCHAR(14) | FK | N | regulation_versions.version_id |
| chapter_number | VARCHAR(20) |  | N |  |
| article_number | VARCHAR(35) |  | N |  |
| article_title | VARCHAR(200) |  | N |  |
| article_text | LONGTEXT |  | N |  |
| page_number | INT |  | N |  |
| extraction_status | VARCHAR(30) |  | N |  |

복합/단일 유일 인덱스: (article_id)

### regulation_chunks

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| chunk_id | VARCHAR(20) | PK | Y |  |
| article_id | VARCHAR(18) | FK | N | regulation_articles.article_id |
| chunk_order | INT |  | N |  |
| chunk_text | TEXT |  | N |  |
| embedding_ref | VARCHAR(200) |  | N |  |
| source_page | INT |  | N |  |

복합/단일 유일 인덱스: (chunk_id)

### regulation_versions

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| version_id | VARCHAR(14) | PK | Y |  |
| regulation_id | VARCHAR(12) | FK | N | regulations.regulation_id |
| revision_number | VARCHAR(20) |  | N |  |
| revision_date | DATE |  | N |  |
| revision_label | VARCHAR(100) |  | N |  |
| effective_date | DATE |  | N |  |
| file_path | VARCHAR(400) |  | N |  |
| file_hash | VARCHAR(64) |  | N |  |
| status | VARCHAR(35) |  | N |  |
| page_count | INT |  | N |  |

복합/단일 유일 인덱스: (version_id)

### regulations

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| regulation_id | VARCHAR(12) | PK | Y |  |
| title | VARCHAR(200) |  | N |  |
| category | VARCHAR(40) |  | N |  |
| regulation_type | VARCHAR(30) |  | N |  |
| owner_dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| access_level | VARCHAR(25) |  | N |  |

복합/단일 유일 인덱스: (regulation_id)

### routing_logs

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| routing_id | VARCHAR(14) | PK | Y |  |
| session_id | VARCHAR(14) | FK | N | chat_sessions.session_id |
| topic_id | VARCHAR(12) | FK | N | business_topics.topic_id |
| confidence_score | DECIMAL(4,3) |  | N |  |
| selected_dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| assigned_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| routing_status | VARCHAR(30) |  | N |  |
| routed_at | DATETIME |  | N |  |

복합/단일 유일 인덱스: (routing_id)

### safety_incidents

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| incident_id | VARCHAR(14) | PK | Y |  |
| reported_at | DATETIME |  | N |  |
| location | VARCHAR(100) |  | N |  |
| incident_type | VARCHAR(70) |  | N |  |
| severity | VARCHAR(20) |  | N |  |
| owner_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| status | VARCHAR(30) |  | N |  |

복합/단일 유일 인덱스: (incident_id)

### satisfaction_surveys

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| survey_id | VARCHAR(14) | PK | Y |  |
| ticket_id | VARCHAR(14) | FK, UK | N | support_tickets.ticket_id |
| score | TINYINT |  | N |  |
| reason_code | VARCHAR(40) |  | N |  |
| comment | VARCHAR(250) |  | N |  |
| submitted_at | DATETIME |  | N |  |

복합/단일 유일 인덱스: (ticket_id), (survey_id)

### support_tickets

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| ticket_id | VARCHAR(14) | PK | Y |  |
| session_id | VARCHAR(14) | FK | N | chat_sessions.session_id |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| topic_id | VARCHAR(12) | FK | N | business_topics.topic_id |
| owner_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| priority | VARCHAR(20) |  | N |  |
| status | VARCHAR(30) |  | N |  |
| created_at | DATETIME |  | N |  |
| closed_at | DATETIME |  | N |  |

복합/단일 유일 인덱스: (ticket_id)

### ticket_events

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| event_id | VARCHAR(14) | PK | Y |  |
| ticket_id | VARCHAR(14) | FK | N | support_tickets.ticket_id |
| actor_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| event_type | VARCHAR(35) |  | N |  |
| previous_status | VARCHAR(25) |  | N |  |
| new_status | VARCHAR(25) |  | N |  |
| occurred_at | DATETIME |  | N |  |

복합/단일 유일 인덱스: (event_id)

### topic_keywords

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| keyword_id | VARCHAR(14) | PK | Y |  |
| topic_id | VARCHAR(12) | FK | N | business_topics.topic_id |
| keyword | VARCHAR(100) |  | N |  |
| synonym | VARCHAR(100) |  | N |  |
| match_weight | DECIMAL(4,2) |  | N |  |

복합/단일 유일 인덱스: (keyword_id)

### topic_ownerships

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| ownership_id | VARCHAR(14) | PK | Y |  |
| topic_id | VARCHAR(12) | FK | N | business_topics.topic_id |
| dept_id | VARCHAR(12) | FK | N | departments.dept_id |
| primary_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| backup_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| approver_employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| priority | TINYINT |  | N |  |
| effective_from | DATE |  | N |  |
| effective_to | DATE |  | N |  |

복합/단일 유일 인덱스: (ownership_id)

### topic_regulations

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| topic_regulation_id | VARCHAR(14) | PK | Y |  |
| topic_id | VARCHAR(12) | FK | N | business_topics.topic_id |
| article_id | VARCHAR(18) | FK | N | regulation_articles.article_id |
| relevance_type | VARCHAR(25) |  | N |  |
| priority | TINYINT |  | N |  |

복합/단일 유일 인덱스: (topic_id, article_id), (topic_regulation_id)

### training_history

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| training_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| course_name | VARCHAR(100) |  | N |  |
| provider | VARCHAR(80) |  | N |  |
| start_date | DATE |  | N |  |
| end_date | DATE |  | N |  |
| completion_status | VARCHAR(25) |  | N |  |

복합/단일 유일 인덱스: (training_id)

### travel_requests

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| travel_id | VARCHAR(14) | PK | Y |  |
| employee_id | VARCHAR(12) | FK | N | employees.employee_id |
| travel_type | VARCHAR(30) |  | N |  |
| destination | VARCHAR(100) |  | N |  |
| start_date | DATE |  | N |  |
| end_date | DATE |  | N |  |
| approval_status | VARCHAR(25) |  | N |  |

복합/단일 유일 인덱스: (travel_id)

### VIEW: v_leave_balance

참조: employees, leave_balances, leave_transactions, leave_types

### VIEW: v_employee_directory

참조: departments, employee_assignments, employee_contacts, employees

### VIEW: v_topic_contact_cards

참조: business_topics, departments, employee_contacts, employees, topic_ownerships

## tool_example

원본: `C:\Users\KDT\Desktop\KDT AI Agent\employee_tools_project\employee_tools\schema.example.sql`

### contacts

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| contact_id | INTEGER | PK | Y |  |
| name | TEXT |  | Y |  |
| department | TEXT |  | Y |  |
| topic | TEXT |  | Y |  |
| keywords_json | TEXT |  | Y |  |
| phone | TEXT |  | N |  |
| email | TEXT |  | N |  |
| is_active | INTEGER |  | Y |  |

복합/단일 유일 인덱스: 없음

### employees

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_id | TEXT | PK | Y |  |
| name | TEXT |  | Y |  |
| department | TEXT |  | Y |  |
| job_title | TEXT |  | N |  |
| travel_grade | TEXT |  | Y |  |

복합/단일 유일 인덱스: (employee_id)

### inquiries

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| inquiry_id | INTEGER | PK | Y |  |
| employee_id | TEXT |  | Y |  |
| question | TEXT |  | Y |  |
| answer | TEXT |  | N |  |
| category | TEXT |  | N |  |
| created_at | TEXT |  | Y |  |
| status | TEXT |  | N |  |

복합/단일 유일 인덱스: 없음

### leave_balances

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| employee_id | TEXT | PK | Y |  |
| leave_type | TEXT | PK | Y |  |
| period_start | TEXT | PK | Y |  |
| period_end | TEXT |  | Y |  |
| granted_days | NUMERIC |  | Y |  |
| carried_days | NUMERIC |  | Y |  |
| adjustment_days | NUMERIC |  | Y |  |
| expired_days | NUMERIC |  | Y |  |

복합/단일 유일 인덱스: (employee_id, leave_type, period_start)

### leave_usage

행 수: DDL만 확인

| 컬럼 | 형식 | 키 | 필수 | 참조 |
| --- | --- | --- | --- | --- |
| usage_id | INTEGER | PK | Y |  |
| employee_id | TEXT |  | Y |  |
| leave_type | TEXT |  | Y |  |
| used_on | TEXT |  | Y |  |
| days | NUMERIC |  | Y |  |
| status | TEXT |  | Y |  |

복합/단일 유일 인덱스: 없음

