import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from scripts.migrate_employee_ids import migrate


class EmployeeIdMigrationTests(unittest.TestCase):
    def test_migrates_both_databases_links_and_json_with_backup_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);paths=[root/'app.db',root/'directory.db']
            for path in paths:
                with closing(sqlite3.connect(path)) as c:
                    c.executescript('CREATE TABLE employees(employee_id TEXT PRIMARY KEY); CREATE TABLE contacts(employee_id TEXT REFERENCES employees(employee_id),photo_path TEXT); CREATE TABLE messages(context_data TEXT);')
                    c.execute("INSERT INTO employees VALUES('KDN0001')")
                    c.execute("INSERT INTO contacts VALUES('KDN0001','assets/KDN0001.svg')")
                    c.execute('INSERT INTO messages VALUES(?)',(json.dumps({'employee_id':'KDN0001','image_url':'/api/users/KDN0001/photo','content':'KDN0001님 질문 원문'}),))
                    c.commit()
            self.assertFalse(migrate(paths,root/'unused')['applied'])
            report=migrate(paths,root/'backup',apply=True)
            self.assertEqual(len(report['backups']),2)
            for path in paths:
                with closing(sqlite3.connect(path)) as c:
                    self.assertEqual(c.execute('SELECT * FROM contacts').fetchone(),('WON0001','assets/KDN0001.svg'))
                    data=json.loads(c.execute('SELECT context_data FROM messages').fetchone()[0])
                    self.assertEqual(data['employee_id'],'WON0001')
                    self.assertEqual(data['image_url'],'/api/users/WON0001/photo')
                    self.assertEqual(data['content'],'KDN0001님 질문 원문')
                    self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertFalse(migrate(paths,root/'second',apply=True)['applied'])

    def test_collision_is_rejected_before_any_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'app.db'
            with closing(sqlite3.connect(path)) as c:
                c.executescript("CREATE TABLE employees(employee_id TEXT PRIMARY KEY); INSERT INTO employees VALUES('KDN0001'),('WON0001');")
                c.commit()
            with self.assertRaisesRegex(ValueError,'충돌'):
                migrate([path],root/'backup',apply=True)
            with closing(sqlite3.connect(path)) as c:
                self.assertEqual(c.execute('SELECT count(*) FROM employees').fetchone()[0],2)
