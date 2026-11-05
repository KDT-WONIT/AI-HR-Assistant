"""원본 사원 데이터셋(CSV)의 연차 잔액·사용 내역을 앱 SQLite에 등록합니다.

    python -m scripts.import_leave_data [--dataset <csv 폴더>] [--dry-run]

- leave_balances.csv  → leave_balances(부여 합계/사용) + leave_balance_details(기본·이월·조정)
- leave_transactions.csv + leave_types.csv → leave_transactions(사용·예정·결재중·취소 내역)
- 원본 사번(KDN####)은 현재 사번(WON####)으로 바꿔 저장하며, 앱 DB에 없는 사원은 건너뜁니다.
- 사용 일수 = 연차를 차감하는 휴가 유형(연차·반차·반반차)의 USED 합계입니다.
"""
import argparse
import csv
import shutil
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.config import resolve_path, settings
from app.identity import canonical_employee_id
from app.integrations.sqlite import connection_scope

SCHEMA = """
CREATE TABLE IF NOT EXISTS leave_balance_details (
    employee_id TEXT NOT NULL, balance_year SMALLINT NOT NULL,
    base_days DECIMAL(6,2) NOT NULL DEFAULT 0, carryover_days DECIMAL(6,2) NOT NULL DEFAULT 0,
    adjusted_days DECIMAL(6,2) NOT NULL DEFAULT 0, PRIMARY KEY (employee_id, balance_year),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id));
CREATE TABLE IF NOT EXISTS leave_transactions (
    transaction_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL, leave_type TEXT NOT NULL,
    deducts_annual_leave SMALLINT NOT NULL DEFAULT 1, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
    days DECIMAL(6,2) NOT NULL, status TEXT NOT NULL, requested_at TEXT,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id));
CREATE INDEX IF NOT EXISTS idx_leave_transactions_employee ON leave_transactions(employee_id, start_date);
"""


def read(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def load(dataset: Path) -> dict:
    csv_dir = dataset / 'csv' if (dataset / 'csv').is_dir() else dataset
    types = {row['leave_type_id']: row for row in read(csv_dir / 'leave_types.csv')}
    balances = read(csv_dir / 'leave_balances.csv')
    transactions = read(csv_dir / 'leave_transactions.csv')
    return {'types': types, 'balances': balances, 'transactions': transactions}


def import_leave_data(dataset: Path, *, dry_run: bool = False) -> dict:
    source = load(dataset)
    now = datetime.now(timezone.utc).isoformat()
    used: dict[tuple[str, int], Decimal] = {}
    for row in source['transactions']:
        kind = source['types'].get(row['leave_type_id'])
        if row['status'] == 'USED' and kind and kind['deducts_annual_leave'] == '1':
            key = (canonical_employee_id(row['employee_id']), int(row['start_date'][:4]))
            used[key] = used.get(key, Decimal(0)) + Decimal(row['days'])
    summary = {'balances': 0, 'transactions': 0, 'skipped_employees': set()}
    with connection_scope(write=True) as connection:
        connection.executescript(SCHEMA)
        known = {row[0] for row in connection.execute('SELECT employee_id FROM employees')}
        for row in source['balances']:
            employee_id, year = canonical_employee_id(row['employee_id']), int(row['year'])
            if employee_id not in known:
                summary['skipped_employees'].add(employee_id)
                continue
            base, carry, adjusted = (Decimal(row[key]) for key in ('granted_days', 'carryover_days', 'adjusted_days'))
            granted, spent = base + carry + adjusted, used.get((employee_id, year), Decimal(0))
            connection.execute(
                'INSERT INTO leave_balances(employee_id,balance_year,granted_days,used_days,updated_at) VALUES(?,?,?,?,?) '
                'ON CONFLICT(employee_id,balance_year) DO UPDATE SET granted_days=excluded.granted_days,'
                'used_days=excluded.used_days,updated_at=excluded.updated_at',
                (employee_id, year, float(granted), float(spent), row.get('updated_at') or now))
            connection.execute(
                'INSERT INTO leave_balance_details(employee_id,balance_year,base_days,carryover_days,adjusted_days) VALUES(?,?,?,?,?) '
                'ON CONFLICT(employee_id,balance_year) DO UPDATE SET base_days=excluded.base_days,'
                'carryover_days=excluded.carryover_days,adjusted_days=excluded.adjusted_days',
                (employee_id, year, float(base), float(carry), float(adjusted)))
            summary['balances'] += 1
        for row in source['transactions']:
            employee_id = canonical_employee_id(row['employee_id'])
            kind = source['types'].get(row['leave_type_id'])
            if employee_id not in known or kind is None:
                summary['skipped_employees'].add(employee_id)
                continue
            connection.execute(
                'INSERT OR REPLACE INTO leave_transactions(transaction_id,employee_id,leave_type,deducts_annual_leave,'
                'start_date,end_date,days,status,requested_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (row['transaction_id'], employee_id, kind['type_name'], int(kind['deducts_annual_leave']),
                 row['start_date'], row['end_date'], float(row['days']), row['status'], row.get('requested_at')))
            summary['transactions'] += 1
        if dry_run:
            connection.rollback()
    summary['skipped_employees'] = sorted(summary['skipped_employees'])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dataset', default=str(settings.employee_dataset_dir))
    parser.add_argument('--dry-run', action='store_true', help='저장하지 않고 건수만 확인')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()
    dataset = resolve_path(args.dataset)
    if not args.dry_run and not args.no_backup:
        db = resolve_path(settings.sqlite_path) if hasattr(settings, 'sqlite_path') else None
        if db and Path(db).is_file():
            backup = Path(db).with_name(Path(db).name + f'.before_leave_{datetime.now():%Y%m%d%H%M%S}')
            shutil.copy2(db, backup)
            print(f'백업: {backup}')
    result = import_leave_data(dataset, dry_run=args.dry_run)
    print(f"연차 잔액 {result['balances']}명, 사용·예정 내역 {result['transactions']}건"
          + (' (미저장 · dry-run)' if args.dry_run else ' 등록/갱신 완료'))
    if result['skipped_employees']:
        print('앱 DB에 없어 건너뜀:', ', '.join(result['skipped_employees'][:10]))


if __name__ == '__main__':
    main()
