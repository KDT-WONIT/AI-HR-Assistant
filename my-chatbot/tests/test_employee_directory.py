"""독립 사원 DB 묶음의 범위, 원본 대조, 사진과 재생성 보호를 검사합니다."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.config import PROJECT_ROOT, settings
from scripts.build_employee_directory import TABLES, build, selected_inserts


class EmployeeDirectoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "logs")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.output = Path(cls.temp.name) / "directory"
        cls.manifest = build(settings.employee_dataset_dir, cls.output)

    def connect(self):
        connection = sqlite3.connect(self.output / "employee_directory.sqlite3")
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        return connection

    def test_only_selected_tables_and_valid_references(self):
        connection = self.connect()
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(names, set(TABLES))
        self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        for table, expected in self.manifest["counts"].items():
            self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0], expected)

    def test_profile_and_department_totals(self):
        connection = self.connect()
        row = connection.execute("SELECT * FROM v_employee_profiles WHERE employee_id='KDN0001'").fetchone()
        self.assertEqual((row["name"], row["department"], row["job_title"]), ("김서연", "인사부", "부서장"))
        self.assertEqual(row["work_email"], "kdn0001@example.com")
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM v_employee_profiles WHERE dept_id IS NOT NULL").fetchone()[0], 100)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM departments WHERE parent_dept_id IS NOT NULL").fetchone()[0], 0)

    def test_latest_photo_metadata_and_included_fallbacks(self):
        for row in self.connect().execute("SELECT * FROM employee_contacts"):
            self.assertEqual(row["photo_status"], "REVIEW_PENDING")
            self.assertEqual(row["photo_file_status"], "NOT_DOWNLOADED")
            self.assertEqual(row["photo_source"], "PEXELS_STOCK_DEMO")
            self.assertEqual(row["photo_alt"], "가상 직원 화면의 스톡 사진 (실제 직원 아님)")
            self.assertTrue((self.output / row["fallback_photo_path"]).is_file())
            self.assertTrue(row["source_page_url"].startswith("https://www.pexels.com/photo/"))
        manifest = json.loads((self.output / "source_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["sources"]), 6)

    def test_existing_database_is_not_overwritten(self):
        path = self.output / "employee_directory.sqlite3"
        previous = path.read_bytes()
        with self.assertRaises(FileExistsError):
            build(settings.employee_dataset_dir, self.output)
        self.assertEqual(path.read_bytes(), previous)

    def test_split_insert_batches_and_quoted_semicolon(self):
        text = "\n".join(f"INSERT INTO `{table}` (`sample`) VALUES ('내용; 유지');" for table in TABLES)
        text += "\nINSERT INTO `employees` (`sample`) VALUES ('두 번째 묶음');\n"
        text += "INSERT INTO `regulations` (`sample`) VALUES ('제외');\n"
        statements = selected_inserts(text)
        self.assertEqual(len(statements["employees"]), 2)
        self.assertNotIn("regulations", statements)


if __name__ == "__main__":
    unittest.main()
