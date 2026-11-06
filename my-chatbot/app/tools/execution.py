from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging
import re

from starlette.concurrency import run_in_threadpool

from app.integrations.sqlite import connection_scope
from app.config import settings
from app.repositories.directory import EmployeeDirectoryRepository
from app.rag.pipeline import RagService
from app.rag.retrieval import RetrievalHints
from app.schemas import ToolArguments, ToolInput, ToolResult
from app.integrations.leave_balance import load_balance
from app.integrations.leave_policy import leave_entitlement
from app.integrations.employee_tools import history_question,inquiry_history,travel_expense


def business_data(tool_id: str, request: ToolInput) -> tuple[dict, str | None]:
    """도구는 조회/계산만 수행합니다. 인사 변경이나 휴가 승인은 하지 않습니다."""
    data = {}
    missing = None
    from app.agent.followups import current_question, situation_statement
    question = current_question(request.question)
    args = ToolArguments.model_validate(request.arguments)
    if situation_statement(question):
        return {'user_situation': question}, None
    from app.agent.tenure import tenure_question, tenure_info
    if tenure_question(question):
        return tenure_data(request, question, tenure_info)
    if history_question(question):
        return {'inquiry_history':inquiry_history(request,args)},None
    args.history_query = None  # 라우터가 일반 질문에도 채울 수 있어, 명시적인 이력 요청만 이력 모드로 처리합니다.
    if tool_id == 'travel_expenses':
        from app.integrations import travel_calc
        if args.trip is None and travel_calc.should_run(question, request.recent_user_messages, request.last_assistant_message):
            return travel_calc_data(request, question)
    if tool_id=='travel_expenses' and (args.trip is not None or any(word in question for word in ('계산','예상','견적','얼마','총액'))):
        from app.agent.travel_estimate_answers import apply_defaults
        if args.trip is not None:
            args.trip,assumptions=apply_defaults(args.trip)
        else:
            assumptions=[]
        result=travel_expense(request,args)
        if isinstance(result,dict) and result.get('status')=='needs_review' and args.trip:
            # 담당자 확인으로 멈추지 않고, 계산 가능한 일반 조건으로 완화해 추정 계산을 한 번 더 시도합니다.
            from app.agent.travel_estimate_answers import relax_for_estimate
            relaxed=relax_for_estimate(args.trip,result.get('message',''))
            if relaxed is not None:
                retry_args=args.model_copy(update={'trip':relaxed[0]})
                retry=travel_expense(request,retry_args)
                if isinstance(retry,dict) and retry.get('status') in {'success','partial'}:
                    assumptions=[*assumptions,'원래 조건: '+result.get('message','담당자 확인이 필요한 조건입니다.'),*relaxed[1]]
                    result=retry
        if isinstance(result,dict) and assumptions:
            result['assumptions']=[*assumptions,*result.get('assumptions',[])]
        if isinstance(result,dict) and result.get('status')=='needs_review' and args.trip:
            result['input']=dict(args.trip)
        return {'travel_expense':result},result.get('error',{}).get('message') if result['status']=='error' else None
    if args.requested_days is None:
        match = re.search(r'(\d+(?:\.\d+)?)\s*일\s*(?:을\s*)?(?:쓰|사용)', question)
        if match:
            days = float(match.group(1))
            if not 0 < days <= 366:
                return {}, '사용 예정 일수는 0보다 크고 366 이하여야 합니다.'
            args.requested_days = days
    own_contact = any(word in question for word in ('내 연락처','내 이메일','내 내선','내 근무지'))
    department_extension = '대표내선' in question.replace(' ','')
    contact_question = not own_contact and not department_extension and is_contact_lookup(question)
    if own_contact or (tool_id in {'hr_employment', 'organization_management'} and any(word in question for word in ('내 정보', '내정보', '내 부서', '내 직급', '입사일', '내 소속'))):
        if request.user_profile:
            data['employee'] = request.user_profile.model_dump(mode='json')
        else:
            missing = '등록된 사용자 정보가 없습니다. 사용자 ID를 확인해주세요.'
    leave_words = ('잔여', '남은', '남아', '일 남', '쓰면', '사용하면')
    entitlement_words = ('며칠', '몇 일', '몇일', '일수', '부여', '발생', '몇 개', '얼마나', '총 ')
    compact_question = question.replace(' ', '')
    annual_question = '연차' in question or (any(word in compact_question for word in ('남은휴가','잔여휴가'))
        and not any(word in question for word in ('배우자','경조','출산','특별','질병')))
    # 라우터가 잔여 연차 질문을 다른 분야로 분류해도 연차 계산 도구는 항상 동작해야 합니다.
    if annual_question and tool_id != 'travel_expenses' and (any(word in question for word in leave_words)
                                    or any(word in question for word in entitlement_words)):
        year = args.year or datetime.now(timezone(timedelta(hours=9))).year
        with connection_scope() as connection:
            row = load_balance(connection, request.employee_id, year)
        profile = request.user_profile
        today = datetime.now(timezone(timedelta(hours=9))).date()
        policy = leave_entitlement(profile.hired_at, today, profile.grade) if row is None and profile and profile.hired_at else None
        if policy is not None:
            # 사용 이력 DB가 없으면 입사일·직급으로 규정상 부여일수를 계산하고, 잔여일수는 단정하지 않습니다.
            data['leave_entitlement'] = policy
            if args.requested_days is not None:
                granted = Decimal(str(policy['granted_days']))
                requested = Decimal(str(args.requested_days))
                data['leave_projection'] = dict(requested_days=float(requested), projected_remaining_days=float(granted - requested),
                                                sufficient=granted >= requested, used_unknown=True,
                                                note='이미 사용한 연차 기록이 없어 부여일수 기준으로만 계산했습니다.')
        elif row is None:
            missing = f'{year}년 연차 부여/사용 데이터가 없습니다. 데이터를 등록해야 잔여일수를 계산할 수 있습니다.'
        else:
            balance = Decimal(str(row['remaining_days']))
            data['leave_balance'] = row
            if args.requested_days is not None:
                requested = Decimal(str(args.requested_days))
                data['leave_projection'] = dict(requested_days=float(requested), projected_remaining_days=float(balance-requested),
                                                sufficient=balance >= requested, note='가정 계산이며 사용/승인 기록을 변경하지 않습니다.')
    directory = EmployeeDirectoryRepository() if settings.user_data_source == 'directory' else None
    if directory is not None and not contact_question and tool_id in {'hr_employment','organization_management'}:
        target = directory.identify_query(question)
        person = directory.get(target) if target else None
        if person is not None:
            data['employee'] = person.model_dump(mode='json')
    if contact_question and directory is not None:
        query = directory.identify_query(question) or args.department
        if not query:
            query = request.user_profile.department if request.user_profile and any(word in question for word in ('우리 부서','내 부서','팀원')) else '인사'
        matches = directory.search(query=query or '',limit=10)
        data['hr_contacts'] = [item.model_dump(mode='json',include={
            'employee_id','name','department','job_title','work_email','extension_number','work_location','roles','image_url',
        }) for item in matches.items]
        if not matches.items:
            missing = '등록된 사원이나 담당자 연락처를 찾지 못했습니다. 이름·사번·부서를 확인해주세요.'
    elif contact_question:
        with connection_scope() as connection:
            rows = connection.execute(
                "SELECT name,department,job_title,work_email,extension_number FROM v_employee_profiles "
                "WHERE department LIKE ? AND contact_visibility='INTERNAL' ORDER BY name LIMIT 10",
                ('%' + (args.department or '인사') + '%',),
            ).fetchall()
        data['hr_contacts'] = [dict(row) for row in rows]
        if not rows:
            missing = '등록된 담당자 연락처가 없습니다.'
    if directory is not None and (department_extension or any(word in question for word in ('부서 목록','조직도','부서 조회','부서 연락','부서 위치','부서 정보','부서별 인원'))):
        query = args.department or directory.identify_query(question) or ''
        person = directory.get(query) if query else None
        query = person.department or '' if person else query
        data['departments'] = [item.model_dump(mode='json') for item in directory.departments(query)]
    elif tool_id == 'organization_management' and any(word in question for word in ('부서 목록', '조직도', '부서 조회', '부서 연락')):
        with connection_scope() as connection:
            rows = connection.execute('SELECT dept_id,dept_name,parent_dept_id,dept_function,location,main_extension FROM departments WHERE is_active=1 ORDER BY dept_id').fetchall()
        data['departments'] = [dict(row) for row in rows]
    return data, missing


from app.agent.intent_guard import is_contact_lookup, drop_unrelated_directory_data  # noqa: E402,F401


def tenure_data(request: ToolInput, question: str, tenure_info) -> tuple[dict, str | None]:
    """근속 질문: 본인(또는 질문에 이름·사번이 있는 사원)의 입사일로 근속 기간을 계산합니다."""
    person = request.user_profile
    if settings.user_data_source == 'directory':
        directory = EmployeeDirectoryRepository()
        target = directory.identify_query(question)
        other = directory.get(target) if target else None
        if other is not None and getattr(other, 'hired_at', None) and (person is None or other.employee_id != person.employee_id):
            person = other
    if person is None or not person.hired_at:
        return {}, '입사일 정보를 찾지 못했습니다. 인사 담당 부서에 확인해주세요.'
    today = datetime.now(timezone(timedelta(hours=9))).date()
    info = tenure_info(person.hired_at, today)
    if info is None:
        return {}, '입사일이 오늘보다 늦어 근속 기간을 계산할 수 없습니다.'
    info['name'] = person.name
    info['is_self'] = request.user_profile is not None and person.employee_id == request.user_profile.employee_id
    return {'tenure': info}, None


def travel_calc_data(request: ToolInput, question: str) -> tuple[dict, str | None]:
    """출장비 계산기: 4가지 입력이 모두 있어야 계산하고, 없으면 빠진 항목을 되묻습니다."""
    import json
    from app.integrations import travel_calc
    inputs = travel_calc.merge_inputs(question, request.recent_user_messages)
    if travel_calc.missing_items(inputs):
        return {'calculator': 'travel_expenses'}, travel_calc.request_message(inputs)
    problem = travel_calc.validate(inputs)
    if problem:
        return {'calculator': 'travel_expenses'}, travel_calc.request_message(inputs, problem)
    grade = None
    try:
        mapping = json.loads(settings.travel_grade_mapping_path.read_text(encoding='utf-8'))
        grade = mapping.get(request.user_profile.grade if request.user_profile else None)
    except (OSError, ValueError):
        pass
    return {'travel_calc': travel_calc.calculate(inputs, grade)}, None


async def execute_domain(tool_id: str, patterns: list[str], request: ToolInput) -> ToolResult:
    data, missing = await run_in_threadpool(business_data, tool_id, request)
    if drop_unrelated_directory_data(request.question, data):
        logging.getLogger(__name__).info('조회 의도가 없어 사원·연락처 데이터를 제외했습니다: tool=%s', tool_id)
    has_directory_data = any(data.get(key) for key in ('employee','hr_contacts','departments'))
    policy_question = any(word in request.question for word in ('규정','기준','절차','방법','자격','지원','신청'))
    # 사원 정보만 묻는 질문에 무관한 규정 검색/LLM 설명을 섞지 않습니다.
    from app.integrations.leave_balance import balance_only_question
    structured = any(data.get(key) for key in ('inquiry_history','travel_expense','travel_calc','calculator','user_situation','tenure')) or (
        bool(data.get('leave_balance')) and balance_only_question(request.question))
    profile = request.user_profile
    hints = RetrievalHints(grade=profile.grade, job_title=profile.job_title, department=profile.department,
                           location=profile.work_location) if profile else None
    sources = [] if structured or (has_directory_data and not policy_question) else await RagService().search(request.question, patterns, hints=hints)
    if missing:
        data['required_information'] = missing
    status = 'needs_input' if missing else 'ok' if sources or any(data.values()) else 'no_result'
    message = missing or (f'관련 문서 조각 {len(sources)}개와 업무 조회 결과를 반환합니다.' if status == 'ok' else '이 분야에서 관련 규정을 찾지 못했습니다.')
    return ToolResult(tool_id=tool_id, status=status, message=message, data=data, sources=sources)
