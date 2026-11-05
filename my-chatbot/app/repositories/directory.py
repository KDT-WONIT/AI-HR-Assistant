"""사원 배포 DB는 읽기 전용으로 연결합니다. 대화 DB/원본 파일을 수정하지 않습니다."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit

from app.config import settings
from app.errors import StorageUnavailable
from app.schemas import DepartmentProfile, EmployeePage, UserProfile


@contextmanager
def directory_connection():
    connection = None
    try:
        path = settings.employee_directory_db.resolve()
        if not path.is_file():
            raise StorageUnavailable('사원 디렉터리 DB가 없습니다. EMPLOYEE_DIRECTORY_DB 경로를 확인해주세요.')
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        yield connection
    except (sqlite3.Error, OSError) as exc:
        raise StorageUnavailable('사원 디렉터리를 읽지 못했습니다. DB 파일과 조회 뷰를 확인해주세요.') from exc
    finally:
        if connection is not None:
            connection.close()


# 사진 URL은 사원 DB의 값이어도 이 호스트(https)만 브라우저에 전달합니다.
REMOTE_PHOTO_HOSTS = {'images.pexels.com'}

PROFILE_SQL = '''SELECT v.*,d.dept_function AS department_function,
                 d.location AS department_location,d.main_extension AS department_extension
                 FROM v_employee_profiles v LEFT JOIN departments d ON d.dept_id=v.dept_id'''


class EmployeeDirectoryRepository:
    def _profiles(self, connection, rows) -> list[UserProfile]:
        if not rows:
            return []
        ids = [row['employee_id'] for row in rows]
        roles = {employee_id:[] for employee_id in ids}
        for row in connection.execute(
            'SELECT er.employee_id,r.role_name FROM employee_roles er JOIN duty_roles r ON r.role_id=er.role_id '
            f'WHERE er.employee_id IN ({",".join("?" for _ in ids)}) '
            "AND er.start_date<=date('now','+9 hours') AND (er.end_date IS NULL OR er.end_date>=date('now','+9 hours')) "
            'ORDER BY r.role_name',ids,
        ):
            roles[row['employee_id']].append(row['role_name'])
        output = []
        for row in rows:
            data = {key:row[key] for key in UserProfile.model_fields if key in row.keys()}
            if row['contact_visibility'] != 'INTERNAL':
                for key in ('work_email','extension_number','work_location'):
                    data[key] = None
            data['roles'] = list(dict.fromkeys(roles[row['employee_id']]))
            data['image_url'] = '/api/users/' + quote(row['employee_id'],safe='') + '/photo'
            data['photo_alt'] = '가상 사원 프로필 이미지'
            output.append(UserProfile.model_validate(data))
        return output

    def get(self, employee_id: str) -> UserProfile | None:
        from app.identity import canonical_employee_id
        employee_id = canonical_employee_id(employee_id)
        with directory_connection() as connection:
            row = connection.execute(PROFILE_SQL + ' WHERE v.employee_id=?',(employee_id,)).fetchone()
            return self._profiles(connection,[row])[0] if row else None

    def search(self, query: str = '', department_id: str | None = None, limit: int = 20, offset: int = 0) -> EmployeePage:
        if not 1 <= limit <= 50 or offset < 0 or len(query) > 100:
            raise ValueError('사원 검색 범위를 확인해주세요.')
        where, parameters = ['1=1'], []
        if query:
            escaped = query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            where.append("(v.employee_id LIKE ? ESCAPE '\\' OR v.name LIKE ? ESCAPE '\\' OR v.department LIKE ? ESCAPE '\\')")
            parameters += ['%' + escaped + '%'] * 3
        if department_id:
            where.append('v.dept_id=?')
            parameters.append(department_id)
        clause = ' WHERE ' + ' AND '.join(where)
        with directory_connection() as connection:
            total = connection.execute('SELECT COUNT(*) FROM v_employee_profiles v' + clause,parameters).fetchone()[0]
            rows = connection.execute(PROFILE_SQL + clause + ' ORDER BY v.employee_id LIMIT ? OFFSET ?',
                                      [*parameters,limit,offset]).fetchall()
            return EmployeePage(items=self._profiles(connection,rows),total=total,limit=limit,offset=offset)

    def departments(self, query: str = '') -> list[DepartmentProfile]:
        with directory_connection() as connection:
            rows = connection.execute(
                'SELECT d.*,COUNT(v.employee_id) AS employee_count FROM departments d '
                'LEFT JOIN v_employee_profiles v ON v.dept_id=d.dept_id '
                "WHERE d.is_active=1 AND instr(d.dept_name,?)>0 GROUP BY d.dept_id ORDER BY d.dept_id",(query,),
            ).fetchall()
            return [DepartmentProfile.model_validate({key:row[key] for key in DepartmentProfile.model_fields}) for row in rows]

    def identify_query(self, question: str) -> str | None:
        """질문에 실제 존재하는 사번/이름/부서명이 포함됐는지 확인합니다."""
        with directory_connection() as connection:
            row = connection.execute('SELECT employee_id,name FROM employees WHERE instr(?,employee_id)>0 OR instr(?,name)>0 '
                                     'ORDER BY length(name) DESC LIMIT 1',(question,question)).fetchone()
            if row:
                return row['employee_id']
            row = connection.execute('SELECT dept_name FROM departments WHERE instr(?,dept_name)>0 '
                                     'ORDER BY length(dept_name) DESC LIMIT 1',(question,)).fetchone()
            return row['dept_name'] if row else None

    def contact_candidates(self, department_ids: list[str]) -> list[dict]:
        if not department_ids:
            return []
        with directory_connection() as connection:
            rows = connection.execute(PROFILE_SQL +
                f' WHERE v.dept_id IN ({",".join("?" for _ in department_ids)}) '
                "AND d.is_active=1 AND v.employment_status='재직' AND v.contact_visibility='INTERNAL' "
                "AND (NULLIF(v.work_email,'') IS NOT NULL OR NULLIF(v.extension_number,'') IS NOT NULL) ORDER BY v.employee_id",
                department_ids).fetchall()
            profiles = self._profiles(connection,rows)
            details = {profile.employee_id:[] for profile in profiles}
            for row in connection.execute(
                'SELECT er.employee_id,r.role_category,r.description FROM employee_roles er '
                'JOIN duty_roles r ON r.role_id=er.role_id '
                "WHERE er.start_date<=date('now','+9 hours') AND (er.end_date IS NULL OR er.end_date>=date('now','+9 hours'))",
            ):
                if row['employee_id'] in details:
                    details[row['employee_id']].append(dict(row))
            return [{'profile':profile,'role_details':details[profile.employee_id]} for profile in profiles]

    def photo(self, employee_id: str) -> Path | None:
        from app.identity import canonical_employee_id
        employee_id = canonical_employee_id(employee_id)
        with directory_connection() as connection:
            row = connection.execute('SELECT photo_path,fallback_photo_path,photo_status,photo_file_status '
                                     'FROM employee_contacts WHERE employee_id=?',(employee_id,)).fetchone()
        if row is None:
            return None
        candidates = []
        approved = row['photo_status'] == 'APPROVED' and row['photo_file_status'] in {'AVAILABLE','DOWNLOADED','LOCAL'}
        # 내려받은 실제 사진 파일이 있으면 사용합니다. 검수 완료분만 쓰려면 EMPLOYEE_PHOTO_REQUIRE_APPROVAL=true.
        if approved or not settings.employee_photo_require_approval:
            candidates.append(row['photo_path'])
        candidates.append(row['fallback_photo_path'])
        root = settings.employee_directory_dir.resolve()
        assets = (root / 'assets').resolve()
        for value in candidates:
            if not value:
                continue
            path = (root / value).resolve()
            if path.is_relative_to(assets) and path.suffix.lower() in {'.svg','.png','.jpg','.jpeg','.webp'} and path.is_file():
                return path
        return None

    def remote_photo_url(self, employee_id: str) -> str | None:
        """로컬 사진이 없을 때 브라우저가 직접 불러올 사원 DB의 사진 주소. 허용된 https 호스트만 반환합니다."""
        from app.identity import canonical_employee_id
        employee_id = canonical_employee_id(employee_id)
        if not settings.employee_photo_remote:
            return None
        with directory_connection() as connection:
            row = connection.execute('SELECT photo_url,photo_status FROM employee_contacts WHERE employee_id=?',
                                     (employee_id,)).fetchone()
        if row is None or not row['photo_url']:
            return None
        if settings.employee_photo_require_approval and row['photo_status'] != 'APPROVED':
            return None
        parsed = urlsplit(row['photo_url'])
        if parsed.scheme != 'https' or parsed.hostname not in REMOTE_PHOTO_HOSTS or parsed.username or parsed.password:
            return None
        return row['photo_url']

    def ping(self):
        with directory_connection() as connection:
            connection.execute('SELECT employee_id FROM v_employee_profiles LIMIT 1').fetchone()
