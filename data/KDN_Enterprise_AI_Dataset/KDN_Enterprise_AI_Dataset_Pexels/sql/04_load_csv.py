"""Import the 43 CSVs into MySQL. Run after 01_create_schema.sql.
Install: python -m pip install mysql-connector-python
Run: python 04_load_csv.py
Enter the MySQL root password securely in your terminal.
"""
from pathlib import Path
import csv, getpass
import mysql.connector

BASE=Path(__file__).resolve().parent.parent
CSV=BASE/'csv'
TABLES=['business_topics', 'departments', 'duty_roles', 'employees', 'absences', 'access_audit_logs', 'asset_registry', 'attendance_records', 'chat_sessions', 'compliance_cases', 'duty_delegations', 'employee_assignments', 'employee_contacts', 'employee_roles', 'expense_claims', 'leave_adjustments', 'leave_balances', 'payroll_monthly', 'performance_reviews', 'personnel_actions', 'procurement_contracts', 'rd_projects', 'regulations', 'safety_incidents', 'topic_keywords', 'topic_ownerships', 'training_history', 'travel_requests', 'asset_assignments', 'benefit_programs', 'chat_messages', 'ip_records', 'regulation_versions', 'routing_logs', 'support_tickets', 'benefit_applications', 'regulation_articles', 'satisfaction_surveys', 'ticket_events', 'leave_types', 'regulation_chunks', 'topic_regulations', 'leave_transactions']

def main():
    pw=getpass.getpass('MySQL 비밀번호: ')
    conn=mysql.connector.connect(host='127.0.0.1',port=3306,user='root',password=pw,database='enterprise_ai_agent',connection_timeout=10,charset='utf8mb4')
    cur=conn.cursor()
    try:
        for table in TABLES:
            with (CSV/(table+'.csv')).open(encoding='utf-8-sig',newline='') as f:
                records=list(csv.DictReader(f))
            if not records: continue
            names=list(records[0])
            cols=','.join('`'+k+'`' for k in names)
            placeholders=','.join(['%s']*len(names))
            sql=f'INSERT IGNORE INTO `{table}` ({cols}) VALUES ({placeholders})'
            params=[tuple(None if r[k]=='' else r[k] for k in names) for r in records]
            for i in range(0,len(params),100): cur.executemany(sql,params[i:i+100])
            conn.commit()
            print(f'{table}: {len(records)} source rows processed')
        print('CSV import finished.')
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close();conn.close()

if __name__=='__main__': main()
