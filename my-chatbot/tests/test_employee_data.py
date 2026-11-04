"""직원 자료의 참조/중복/기간/사진 경로와 MySQL 적재를 검증합니다."""

import copy
import csv
import os
import tempfile
import unittest
from pathlib import Path

from app.config import settings
from app.errors import StorageUnavailable
from app.integrations.mysql import connection_scope
from scripts.seed_employees import FIELDS, insert_dataset, load_dataset


class EmployeeDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dataset = Path(self.temp.name)
        self.rows = {
            "departments": [dict(dept_id="D001", dept_name="인사부", is_active="1")],
            "duty_roles": [dict(role_id="R001", role_name="부서장")],
            "employees": [dict(employee_id="KDN0001", employee_name="김서연", grade="2직급",
                               hire_date="2006-01-05", employment_type="정규직", employment_status="재직")],
            "employee_assignments": [dict(assignment_id="EA0001", employee_id="KDN0001", dept_id="D001",
                                          position_title="부서장", start_date="2006-01-05", is_primary="1")],
            "employee_roles": [dict(employee_role_id="ER0001", employee_id="KDN0001", role_id="R001", start_date="2006-01-05")],
            "employee_contacts": [dict(employee_id="KDN0001", work_email="kdn0001@example.com",
                                       contact_visibility="INTERNAL", photo_path="assets/photos/KDN0001.jpg",
                                       photo_url="https://images.pexels.com/photos/1/test.jpeg",
                                       photo_status="REVIEW_PENDING", photo_source="PEXELS_STOCK_DEMO")],
        }
        (self.dataset / "docs").mkdir()
        with (self.dataset / "docs" / "employee_photo_manifest_100.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["employee_id", "source_page_url", "license_url"])
            writer.writerow(["KDN0001", "https://www.pexels.com/photo/1/", "https://www.pexels.com/license/"])
        (self.dataset / "assets" / "profiles").mkdir(parents=True)
        (self.dataset / "assets" / "profiles" / "KDN0001.svg").write_text("<svg/>", encoding="utf-8")

    def load(self):
        (self.dataset / "csv").mkdir(exist_ok=True)
        for table, rows in self.rows.items():
            with (self.dataset / "csv" / f"{table}.csv").open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS[table])
                writer.writeheader()
                writer.writerows(rows)
        return load_dataset(self.dataset)

    def test_photo_metadata_and_missing_original_are_preserved(self):
        tables = self.load()
        contact = tables["employee_contacts"][0]
        self.assertEqual(contact["photo_status"], "REVIEW_PENDING")
        self.assertEqual(contact["photo_file_status"], "NOT_DOWNLOADED")
        self.assertTrue((self.dataset / contact["fallback_photo_path"]).is_file())
        self.assertEqual(contact["license_url"], "https://www.pexels.com/license/")

    def test_unknown_parent_and_department_cycle_are_rejected(self):
        self.rows["employee_assignments"][0]["dept_id"] = "MISSING"
        with self.assertRaises(ValueError):
            self.load()
        self.rows["employee_assignments"][0]["dept_id"] = "D001"
        self.rows["departments"][0]["parent_dept_id"] = "D001"
        with self.assertRaises(ValueError):
            self.load()

    def test_duplicate_employee_and_overlapping_primary_periods_are_rejected(self):
        self.rows["employees"] *= 2
        with self.assertRaises(ValueError):
            self.load()
        self.rows["employees"] = self.rows["employees"][:1]
        self.rows["employee_assignments"].append({**self.rows["employee_assignments"][0], "assignment_id": "EA0002"})
        with self.assertRaises(ValueError):
            self.load()

    def test_photo_path_escape_and_invalid_dates_are_rejected(self):
        self.rows["employee_contacts"][0]["photo_path"] = "../outside.jpg"
        with self.assertRaises(ValueError):
            self.load()
        self.rows["employee_contacts"][0]["photo_path"] = "assets/photos/KDN0001.jpg"
        self.rows["employee_assignments"][0]["end_date"] = "2000-01-01"
        with self.assertRaises(ValueError):
            self.load()

    def test_children_are_sorted_after_parent_departments(self):
        self.rows["departments"].insert(0, dict(dept_id="D002", dept_name="인사팀", parent_dept_id="D001", is_active="1"))
        self.assertEqual([row["dept_id"] for row in self.load()["departments"]], ["D001", "D002"])


@unittest.skipUnless(os.getenv("RUN_MYSQL_TESTS") == "1", "전용 MySQL 테스트 DB 설정 시 실행")
class EmployeeMySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not settings.mysql_database.endswith("_test"):
            raise RuntimeError("직원 MySQL 테스트는 _test 전용 DB에서만 실행하세요.")
        from scripts.init_db import initialize
        initialize()
        cls.tables = load_dataset(settings.employee_dataset_dir)
        insert_dataset(cls.tables)

    def test_profile_join_and_existing_user_lookup(self):
        from app.repositories.users import MySQLUserRepository
        profile = MySQLUserRepository().get("KDN0001")
        self.assertEqual((profile.name, profile.department, profile.job_title), ("김서연", "인사부", "부서장"))
        self.assertIsNone(MySQLUserRepository().get("NOT-A-USER"))
        with connection_scope() as connection, connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM v_employee_profiles WHERE employee_id = %s", ("KDN0001",))
            row = cursor.fetchone()
            self.assertEqual(row["photo_status"], "REVIEW_PENDING")
            self.assertTrue(row["source_page_url"].startswith("https://www.pexels.com/"))
            cursor.execute("SELECT COUNT(*) AS total FROM v_employee_profiles WHERE employee_id LIKE 'KDN%'")
            self.assertEqual(cursor.fetchone()["total"], 100)

    def test_reimport_adds_nothing(self):
        self.assertTrue(all(count == 0 for count in insert_dataset(self.tables).values()))

    def test_conflicting_contact_rolls_back_other_tables(self):
        suffix = "ROLLBACK01"
        employee = {**self.tables["employees"][0], "employee_id": suffix}
        contact = {**self.tables["employee_contacts"][0], "employee_id": suffix}
        # 기존 이메일과의 충돌로 앞서 추가한 직원까지 롤백되는지 확인합니다.
        with self.assertRaises(StorageUnavailable):
            insert_dataset({"employees": [employee], "employee_contacts": [contact]})
        with connection_scope() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM employees WHERE employee_id = %s", (suffix,))
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_missing_employee_reference_is_rejected(self):
        contact = copy.deepcopy(self.tables["employee_contacts"][0])
        contact.update(employee_id="MISSING-EMP", work_email="missing@example.com")
        with self.assertRaises(StorageUnavailable):
            insert_dataset({"employee_contacts": [contact]})


if __name__ == '__main__':
    unittest.main()
