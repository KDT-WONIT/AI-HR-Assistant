import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, settings, Settings
from app.errors import StorageUnavailable
from app.repositories.directory import EmployeeDirectoryRepository, directory_connection
from app.schemas import ToolInput


class DirectoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        (root/'assets/profiles').mkdir(parents=True)
        (root/'assets/profiles/P1.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>',encoding='utf-8')
        (root/'assets/profiles/P2.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>',encoding='utf-8')
        self.path=root/'employee_directory.sqlite3'
        with closing(sqlite3.connect(self.path)) as c, c:
            c.executescript((PROJECT_ROOT/'database/employee_directory/sqlite_schema.sql').read_text(encoding='utf-8'))
            c.execute("INSERT INTO departments(dept_id,dept_name,location,main_extension) VALUES('D1','인사부','본사','2010')")
            c.execute("INSERT INTO departments(dept_id,dept_name,location,main_extension) VALUES('D2','기술부','연구소','2020')")
            c.execute("INSERT INTO duty_roles(role_id,role_name) VALUES('R1','실무담당자')")
            for employee,name,dept,visibility in [('P1','김테스트','D1','INTERNAL'),('P2','이테스트','D2','PRIVATE')]:
                c.execute('INSERT INTO employees(employee_id,name,hired_at,employment_status,created_at) VALUES(?,?,?,?,?)',(employee,name,'2020-01-01','재직','2020-01-01'))
                c.execute('INSERT INTO employee_assignments(assignment_id,employee_id,dept_id,position_title,start_date) VALUES(?,?,?,?,?)',
                          ('A'+employee,employee,dept,'담당자','2020-01-01'))
                c.execute('INSERT INTO employee_contacts(employee_id,work_email,extension_number,contact_visibility,fallback_photo_path) VALUES(?,?,?,?,?)',
                          (employee,employee.lower()+'@example.com','2101',visibility,'assets/profiles/'+employee+'.svg'))
            c.execute("INSERT INTO employee_roles(employee_role_id,employee_id,role_id,start_date) VALUES('ER1','P1','R1','2020-01-01')")
        self.config=replace(settings,user_data_source='directory',employee_directory_dir=root,employee_directory_db=self.path)
        for target in ['app.repositories.directory.settings','app.repositories.users.settings','app.tools.execution.settings','app.api.routes.settings']:
            item=patch(target,self.config);item.start();self.addCleanup(item.stop)
        self.repository=EmployeeDirectoryRepository()

    def test_current_profile_has_contacts_department_role_and_local_image(self):
        profile=self.repository.get('P1')
        self.assertEqual((profile.name,profile.department,profile.job_title),('김테스트','인사부','담당자'))
        self.assertEqual(profile.work_email,'p1@example.com')
        self.assertEqual(profile.department_extension,'2010')
        self.assertEqual(profile.roles,['실무담당자'])
        self.assertEqual(profile.image_url,'/api/users/P1/photo')
        self.assertTrue(self.repository.photo('P1').is_file())

    def test_search_pagination_department_filter_and_literal_search(self):
        self.assertEqual(self.repository.search('김테스트').items[0].employee_id,'P1')
        self.assertEqual(self.repository.search(department_id='D2').items[0].employee_id,'P2')
        self.assertEqual(self.repository.search(limit=1,offset=1).total,2)
        self.assertEqual(self.repository.search("' OR 1=1--").total,0)
        self.assertEqual(self.repository.search('%').total,0)
        self.assertEqual(self.repository.identify_query('김테스트 연락처 알려줘'),'P1')
        self.assertEqual(self.repository.identify_query('기술부 담당자 연락처'),'기술부')

    def test_departments_count_profiles_and_private_contacts_are_hidden(self):
        departments=self.repository.departments()
        self.assertEqual(sum(item.employee_count for item in departments),2)
        self.assertEqual(self.repository.departments('인사')[0].main_extension,'2010')
        private=self.repository.get('P2')
        self.assertIsNone(private.work_email)
        self.assertIsNone(private.extension_number)

    def test_recommendation_candidates_exclude_hidden_retired_and_missing_contacts(self):
        self.assertEqual([item['profile'].employee_id for item in self.repository.contact_candidates(['D1','D2'])],['P1'])
        with closing(sqlite3.connect(self.path)) as c,c:
            c.execute("UPDATE employees SET employment_status='퇴직' WHERE employee_id='P1'")
        self.assertEqual(self.repository.contact_candidates(['D1','D2']),[])

    def test_read_only_access_does_not_create_or_modify_database(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.repository.get('P1');self.repository.search();self.repository.departments()
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        with self.assertRaises(StorageUnavailable):
            with directory_connection() as connection:
                connection.execute("UPDATE employees SET name='변경'")
        self.path.unlink()
        with self.assertRaises(StorageUnavailable): self.repository.get('P1')
        self.assertFalse(self.path.exists())

    def test_photo_path_cannot_escape_assets_and_unapproved_remote_photo_is_not_loaded(self):
        outside=self.config.employee_directory_dir/'secret.svg'
        outside.write_text('<svg/>',encoding='utf-8')
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute("UPDATE employee_contacts SET fallback_photo_path='secret.svg',photo_url='https://example.com/image.jpg' WHERE employee_id='P1'")
        self.assertIsNone(self.repository.photo('P1'))
        self.assertIsNone(self.repository.photo('UNKNOWN'))

    def test_remote_photo_url_comes_from_employee_data_for_allowed_https_hosts_only(self):
        good='https://images.pexels.com/photos/1/pexels-photo-1.jpeg?w=600'
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute("UPDATE employee_contacts SET photo_url=? WHERE employee_id='P1'",(good,))
        self.assertEqual(self.repository.remote_photo_url('P1'),good)
        self.assertIsNone(self.repository.remote_photo_url('P2'))
        self.assertIsNone(self.repository.remote_photo_url('UNKNOWN'))
        for bad in ('http://images.pexels.com/a.jpg','https://evil.example/a.jpg','https://images.pexels.com@evil.example/a.jpg',
                    'https://user:pw@images.pexels.com/a.jpg','javascript:alert(1)'):
            with self.subTest(url=bad):
                with closing(sqlite3.connect(self.path)) as c, c:
                    c.execute("UPDATE employee_contacts SET photo_url=? WHERE employee_id='P1'",(bad,))
                self.assertIsNone(self.repository.remote_photo_url('P1'))

    def test_remote_photo_can_be_disabled_or_limited_to_approved_photos(self):
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute("UPDATE employee_contacts SET photo_url='https://images.pexels.com/photos/1/a.jpeg',photo_status='REVIEW_PENDING' WHERE employee_id='P1'")
        for change in ({'employee_photo_remote':False},{'employee_photo_require_approval':True}):
            with self.subTest(change=change), patch('app.repositories.directory.settings',replace(self.config,**change)):
                self.assertIsNone(self.repository.remote_photo_url('P1'))

    def test_photo_endpoint_prefers_downloaded_file_then_employee_photo_url_then_local_icon(self):
        from app.api import routes
        (self.config.employee_directory_dir/'assets/photos').mkdir()
        (self.config.employee_directory_dir/'assets/photos/P1.jpg').write_bytes(b'\xff\xd8\xff\xe0fake-jpeg')
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute("UPDATE employee_contacts SET photo_path='assets/photos/P1.jpg',photo_status='REVIEW_PENDING',photo_file_status='NOT_DOWNLOADED',"
                      "photo_url='https://images.pexels.com/photos/1/a.jpeg' WHERE employee_id='P1'")
            c.execute("UPDATE employee_contacts SET photo_url='https://images.pexels.com/photos/2/b.jpeg' WHERE employee_id='P2'")
        app=FastAPI()
        app.include_router(routes.router,prefix='/api')
        with TestClient(app,follow_redirects=False) as client:
            local=client.get('/api/users/P1/photo')
            self.assertEqual((local.status_code,local.headers['content-type']),(200,'image/jpeg'))
            remote=client.get('/api/users/P2/photo')
            self.assertEqual(remote.status_code,307)
            self.assertEqual(remote.headers['location'],'https://images.pexels.com/photos/2/b.jpeg')
            icon=client.get('/api/users/P2/photo?fallback=true')
            self.assertEqual(icon.status_code,200)
            self.assertIn('image/svg+xml',icon.headers['content-type'])
            with patch('app.repositories.directory.settings',replace(self.config,employee_photo_require_approval=True)):
                strict=client.get('/api/users/P1/photo')
                self.assertIn('image/svg+xml',strict.headers['content-type'])

    def test_factory_uses_independent_directory(self):
        from app.repositories.users import create_user_repository
        self.assertIsInstance(create_user_repository('sqlite'),EmployeeDirectoryRepository)
        config=Settings.from_env({'EMPLOYEE_DIRECTORY_DIR':'./custom-directory','USER_DATA_SOURCE':'directory'})
        self.assertEqual(config.employee_directory_db,PROJECT_ROOT/'custom-directory/employee_directory.sqlite3')

    def test_business_tools_read_contacts_and_departments_from_directory(self):
        from app.tools.execution import business_data
        request=ToolInput(question='김테스트 연락처',employee_id='P1',conversation_id=uuid4(),user_profile=self.repository.get('P1'))
        data,missing=business_data('hr_employment',request)
        self.assertIsNone(missing)
        self.assertEqual(data['hr_contacts'][0]['work_email'],'p1@example.com')
        request.question='부서 목록과 대표 내선'
        data,missing=business_data('organization_management',request)
        self.assertEqual(len(data['departments']),2)
        request.question='인사부 대표 내선'
        data,missing=business_data('organization_management',request)
        self.assertNotIn('hr_contacts',data)
        self.assertEqual(data['departments'][0]['main_extension'],'2010')

    def test_directory_profile_is_included_in_model_context(self):
        from app.integrations.ollama import OllamaClient
        from app.schemas import AnswerContext
        context=AnswerContext(question='규정?',employee_id='P1',user_profile=self.repository.get('P1'),user_profile_status='found')
        text=OllamaClient.build_messages(context)[-1]['content']
        self.assertNotIn('p1@example.com',text)  # 답변 모델에는 연락처·사진 같은 불필요한 정보를 넘기지 않습니다.
        self.assertIn('tenure',text)
        self.assertIn('실무담당자',text)
        self.assertIn('인사부',text)

    def test_leave_ledger_keeps_foreign_key_reference_without_copying_the_directory(self):
        from scripts.import_leave_balances import import_balances
        from app.integrations.sqlite import connection_scope
        config=replace(self.config,sqlite_path=self.config.employee_directory_dir/'chat.sqlite3')
        csv=self.config.employee_directory_dir/'leave.csv'
        csv.write_text('employee_id,year,granted_days,used_days\nP1,2026,15,2\n',encoding='utf-8')
        with patch('scripts.import_leave_balances.settings',config),patch('app.integrations.sqlite.settings',config):
            self.assertEqual(import_balances(csv),1)
            with connection_scope() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM employees').fetchone()[0],1)
                self.assertEqual(c.execute('SELECT granted_days-used_days FROM leave_balances').fetchone()[0],13)
            csv.write_text('employee_id,year,granted_days,used_days\nUNKNOWN,2026,15,2\n',encoding='utf-8')
            with self.assertRaises(ValueError): import_balances(csv)

    def test_http_directory_endpoints_serve_data_and_images_without_exposing_database(self):
        from app.api import routes
        # 읽기 전용 디렉터리 API의 검사이며 MCP 수명 주기는 별도 MCP 검사에서 다룹니다.
        app=FastAPI()
        app.include_router(routes.router,prefix='/api')
        with patch.object(routes.service,'users',self.repository), TestClient(app) as client:
            self.assertEqual(client.get('/api/users/P1').json()['profile']['name'],'김테스트')
            self.assertEqual(client.get('/api/employees?query=김테스트').json()['total'],1)
            self.assertEqual(len(client.get('/api/departments').json()),2)
            photo=client.get('/api/users/P1/photo')
            self.assertEqual(photo.status_code,200)
            self.assertIn('image/svg+xml',photo.headers['content-type'])
            self.assertEqual(client.get('/api/users/UNKNOWN/photo').status_code,404)
            self.assertEqual(client.get('/api/employees?limit=500').status_code,422)
            self.assertEqual(client.get('/employee_directory.sqlite3').status_code,404)



if __name__ == '__main__':
    unittest.main()
