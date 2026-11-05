"""SQLite 사번을 KDN→WON으로 전환합니다. 기본은 미리보기, --apply 시 백업 후 적용합니다."""
import argparse
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def rewrite_json(value, mapping):
    if isinstance(value, dict):
        return {mapping.get(key, key): rewrite_json(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_json(item, mapping) for item in value]
    if isinstance(value, str):
        if value in mapping:
            return mapping[value]
        return re.sub(r'(/api/users/)(KDN\d+)(/photo)',
                      lambda match: match[1]+mapping.get(match[2],match[2])+match[3],value)
    return value


def migrate(paths, backup_dir, *, apply=False):
    paths = list(dict.fromkeys(Path(path).resolve() for path in paths))
    if any(not path.is_file() for path in paths):
        raise ValueError('기존 DB 파일만 전환할 수 있습니다.')
    connection = sqlite3.connect(paths[0], timeout=30)
    connection.row_factory = sqlite3.Row
    aliases = ['main']
    try:
        for index,path in enumerate(paths[1:],1):
            alias=f'db{index}'; connection.execute(f'ATTACH DATABASE ? AS {alias}',(str(path),)); aliases.append(alias)
        tables=[]; mapping={}
        for alias in aliases:
            for row in connection.execute(f"SELECT name FROM {alias}.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                name=row['name']; quoted='"'+name.replace('"','""')+'"'
                columns=[r['name'] for r in connection.execute(f'PRAGMA {alias}.table_info({quoted})')]
                tables.append((alias,quoted,columns))
                if 'employee_id' in columns:
                    ids=[r[0] for r in connection.execute(f'SELECT DISTINCT employee_id FROM {alias}.{quoted}')]
                    for identifier in ids:
                        if identifier and re.fullmatch(r'KDN\d+',identifier):
                            mapping[identifier]='WON'+identifier[3:]
        # 같은 DB의 한 테이블 안에 새 사번이 이미 있다면 덮어쓰지 않습니다.
        for alias,table,columns in tables:
            if 'employee_id' in columns:
                ids={r[0] for r in connection.execute(f'SELECT DISTINCT employee_id FROM {alias}.{table}')}
                if any(old in ids and new in ids for old,new in mapping.items()):
                    raise ValueError(f'사번 충돌: {alias}.{table}')
        report={'databases':[str(p) for p in paths],'employee_count':len(mapping),'mapping':mapping,'applied':False}
        if not apply or not mapping:
            return report
        backup_dir=Path(backup_dir); backup_dir.mkdir(parents=True,exist_ok=False)
        backups=[]
        for index,path in enumerate(paths):
            destination=backup_dir/f'{index}-{path.name}'
            with closing(sqlite3.connect(path)) as source,closing(sqlite3.connect(destination)) as target:
                source.backup(target)
            backups.append(str(destination))
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('PRAGMA defer_foreign_keys=ON')
        for alias,table,columns in tables:
            if 'employee_id' in columns:
                connection.executemany(f'UPDATE {alias}.{table} SET employee_id=? WHERE employee_id=?',
                                       [(new,old) for old,new in mapping.items()])
            for column in ('context_data','end_result','payload'):
                if column not in columns:
                    continue
                for row in connection.execute(f'SELECT rowid AS _rowid,"{column}" AS data FROM {alias}.{table} WHERE "{column}" IS NOT NULL').fetchall():
                    data=json.loads(row['data']); updated=rewrite_json(data,mapping)
                    if data!=updated:
                        connection.execute(f'UPDATE {alias}.{table} SET "{column}"=? WHERE rowid=?',
                                           (json.dumps(updated,ensure_ascii=False),row['_rowid']))
        for alias in aliases:
            if connection.execute(f'PRAGMA {alias}.foreign_key_check').fetchall():
                raise ValueError(f'외래키 검사 실패: {alias}')
        connection.commit()
        report.update(applied=True,backups=backups)
        (backup_dir/'migration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return report
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main():
    from app.config import settings
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--apply',action='store_true'); args=parser.parse_args()
    if settings.storage_backend!='sqlite':
        parser.error('현재 전환기는 SQLite 서비스용입니다.')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report=migrate([settings.sqlite_path,settings.employee_directory_db],settings.logs_dir/'backups'/f'employee-ids-{stamp}',apply=args.apply)
    print(json.dumps({key:value for key,value in report.items() if key!='mapping'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
