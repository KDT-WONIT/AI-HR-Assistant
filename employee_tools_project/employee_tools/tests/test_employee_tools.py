"""도메인 계산, 사원별 접근 범위, 입력 오류를 외부 서버 없이 검증합니다."""
import json
from pathlib import Path
import sqlite3

import pytest

from employee_tools.common import ToolError, create_employee_context
from employee_tools.database import SqliteRepository
from employee_tools.leave_status_tool import get_leave_status
from employee_tools.contact_lookup_tool import get_responsible_contact
from employee_tools.inquiry_history_tool import search_inquiry_history
from employee_tools.travel_expense_tool import calculate_travel_expense
from employee_tools.tool_registry import EmployeeTools


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / 'employees.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.executescript((Path(__file__).resolve().parents[1] / 'schema.example.sql').read_text(encoding='utf-8'))
        connection.executemany('INSERT INTO employees VALUES (?,?,?,?,?)', [
            ('A001', '테스트 사원 A', '개발', '사원', 'grade_3'),
            ('B001', '테스트 사원 B', '인사', '임원', 'executive')])
        connection.execute('INSERT INTO leave_balances VALUES (?,?,?,?,?,?,?,?)',
                           ('A001','annual','2026-06-15','2027-06-14',15,2,0,1))
        connection.executemany('INSERT INTO leave_usage VALUES (?,?,?,?,?,?)', [
            (1,'A001','annual','2026-07-01',1,'approved'),
            (2,'A001','annual','2026-08-01',0.5,'approved'),
            (3,'A001','annual','2026-09-01',0.25,'approved'),
            (4,'A001','annual','2026-12-01',2,'approved'),
            (5,'A001','annual','2026-12-02',1,'pending'),
            (6,'A001','annual','2026-08-02',3,'cancelled'),
            (7,'A001','annual','2026-08-03',2,'rejected'),
            (8,'B001','annual','2026-08-03',9,'approved')])
        connection.executemany('INSERT INTO contacts VALUES (?,?,?,?,?,?,?,?)', [
            (1,'휴가 담당','인사','휴가','["연차", "이월"]','000-1111','leave@example.test',1),
            (2,'퇴직 담당','인사','퇴직','["퇴직"]','000-2222',None,0)])
        connection.executemany('INSERT INTO inquiries VALUES (?,?,?,?,?,?,?)', [
            (1,'A001','연차 이월 문의','이월 기준 안내','휴가','2026-10-01T09:00:00','closed'),
            (2,'A001','출장 신청 문의',None,'여비','2026-10-02T09:00:00','open'),
            (3,'B001','급여 비공개 문의','다른 사원의 비공개 답변','급여','2026-10-03T09:00:00','closed')])
    return SqliteRepository(path)


@pytest.fixture
def context(repository):
    return create_employee_context('A001', repository)


def domestic(**changes):
    trip = dict(trip_type='domestic', start_date='2026-11-04', end_date='2026-11-05',
                destination_city='서울', distance_km=600, same_city=False,
                domestic_region_type='special_city', transport_cost_krw=50000)
    trip.update(changes)
    return trip


def overseas(**changes):
    trip = dict(trip_type='overseas', start_date='2026-11-04', end_date='2026-11-05',
                destination_city='도쿄', destination_country='일본', lodging_nights=1, meal_days=2,
                transport_cost_krw=600000, exchange_rate_krw_per_usd=1400,
                approval_date='2026-10-30', exchange_rate_date='2026-10-30',
                exchange_rate_basis='hana_cash_buy_opening')
    trip.update(changes)
    return trip


def test_leave_accounting_and_anniversary_period(context):
    result = get_leave_status(as_of='2026-11-04', planned_days=0.25, context=context)['data']
    assert result['period_start'] == '2026-06-15'
    assert result['entitlement_days'] == 16
    assert result['used_days'] == 1.75
    assert result['scheduled_days'] == 2
    assert result['pending_days'] == 1
    assert result['remaining_days'] == 12.25
    assert result['remaining_after_plan'] == 12
    assert len(result['usage']) == 7


def test_leave_plan_does_not_write(context):
    before = context.repository.db_path.read_bytes()
    result = get_leave_status(as_of='2026-11-04', planned_days=20, context=context)
    assert not result['data']['plan_fits_balance']
    assert context.repository.db_path.read_bytes() == before


@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf')])
def test_invalid_leave_plan(context, value):
    assert get_leave_status(planned_days=value, context=context)['status'] == 'error'


def test_unknown_employee(repository):
    with pytest.raises(ToolError):
        create_employee_context('MISSING', repository)
    with pytest.raises(ToolError):
        create_employee_context("' OR 1=1 --", repository)


def test_employee_scope_in_history(context):
    own = search_inquiry_history(context=context)['data']['results']
    assert {row['inquiry_id'] for row in own} == {1, 2}
    assert search_inquiry_history('급여', context=context)['data']['results'] == []
    assert search_inquiry_history("%' OR 1=1 --", context=context)['data']['results'] == []


def test_history_keyword(context):
    result = search_inquiry_history('연차 이월', context=context)['data']
    assert result['count'] == 1 and result['results'][0]['inquiry_id'] == 1


def test_mistaken_sql_cannot_expose_other_employee(context):
    context.repository.queries['inquiries'] = 'SELECT * FROM inquiries'
    result = search_inquiry_history(context=context)
    assert result['error']['code'] == 'EMPLOYEE_SCOPE_ERROR'


def test_contact_does_not_invent_people(context):
    result = get_responsible_contact('연차 이월 관련 문의', context=context)['data']
    assert result['contacts'][0]['name'] == '휴가 담당'
    assert get_responsible_contact('알 수 없는 장비', context=context)['status'] == 'not_found'
    assert get_responsible_contact('퇴직', context=context)['status'] == 'not_found'


def test_domestic_cap_is_budget(context):
    result = calculate_travel_expense(domestic(), context=context)['data']
    assert result['estimated_total_krw'] == '260000.00'
    assert result['lodging_basis'] == 'ceiling_budget'
    assert result['lodging_cap_per_night'] == '100000.00'


@pytest.mark.parametrize(('region','cap'), [('special_city','100000.00'), ('metropolitan_city','90000.00'),
                                           ('special_autonomous','80000.00'), ('other','70000.00')])
def test_domestic_regional_caps(context, region, cap):
    result = calculate_travel_expense(domestic(domestic_region_type=region), context=context)
    assert result['data']['lodging_cap_per_night'] == cap


def test_one_day_meals_are_two_thirds(context):
    result = calculate_travel_expense(domestic(end_date='2026-11-04'), context=context)['data']
    assert result['meal_allowance'] == '20000.00'
    assert result['estimated_total_krw'] == '95000.00'


@pytest.mark.parametrize(('distance','total'), [(9.9,'20000.00'), (10,'30000.00'), (25,'40000.00'), (49.9,'40000.00')])
def test_near_distance_boundaries(context, distance, total):
    result = calculate_travel_expense(domestic(end_date='2026-11-04', distance_km=distance), context=context)
    assert result['data']['estimated_total_krw'] == total


def test_conflicting_company_car_clause_is_not_guessed(context):
    result = calculate_travel_expense(domestic(end_date='2026-11-04', distance_km=20,
                                               transport_mode='company_car'), context=context)
    assert result['status'] == 'needs_review' and result['estimated_total_krw'] is None


def test_domestic_long_stay_arrival_day(context):
    result = calculate_travel_expense(domestic(start_date='2026-11-01', end_date='2026-12-02'), context=context)
    assert result['data']['daily_allowance'] == '797500.00'


def test_overseas_grade_currency_and_rate_date(context):
    result = calculate_travel_expense(overseas(), context=context)['data']
    assert result['daily_allowance'] == '70.00'
    assert result['meal_allowance'] == '192.00'
    assert result['lodging_budget'] == '140.00'
    assert result['estimated_total_krw'] == '1162800.00'
    assert result['overseas_region_grade'] == 'A'
    bad = calculate_travel_expense(overseas(exchange_rate_date='2026-11-01'), context=context)
    assert bad['error']['code'] == 'EXCHANGE_RATE_DATE_MISMATCH'


def test_switzerland_all_cities_are_a(context):
    result = calculate_travel_expense(overseas(destination_city='제네바', destination_country='스위스'), context=context)
    assert result['data']['overseas_region_grade'] == 'A'


def test_other_foreign_city_is_b(context):
    result = calculate_travel_expense(overseas(destination_city='베를린', destination_country='독일'), context=context)
    assert result['data']['overseas_region_grade'] == 'B'
    assert result['data']['lodging_cap_per_night'] == '120.00'


def test_missing_costs_do_not_become_zero(context):
    for trip in [domestic(transport_cost_krw=None), overseas(exchange_rate_krw_per_usd=None)]:
        result = calculate_travel_expense(trip, context=context)
        assert result['status'] == 'partial' and result['data']['estimated_total_krw'] is None


def test_executive_actual_lodging_requires_expected_price(repository):
    context = create_employee_context('B001', repository)
    result = calculate_travel_expense(domestic(), context=context)
    assert result['status'] == 'partial'
    assert 'lodging_cost_per_night' in result['data']['missing_inputs']


def test_rental_vehicle_halves_daily_allowance(context):
    result = calculate_travel_expense(domestic(transport_mode='rental_car'), context=context)
    assert result['data']['daily_allowance'] == '25000.00'


def test_invalid_and_exceptional_trips(context):
    assert calculate_travel_expense(domestic(end_date='2026-11-03'), context=context)['status'] == 'error'
    assert calculate_travel_expense(domestic(special_conditions=['임원 동행']), context=context)['status'] == 'needs_review'
    assert calculate_travel_expense(overseas(end_date='2026-12-05'), context=context)['status'] == 'needs_review'
    assert calculate_travel_expense(domestic(travel_grade='executive'), context=context)['status'] == 'error'


def test_registry_disallows_employee_switch(repository):
    tools = EmployeeTools('A001', repository)
    assert len(tools.definitions) == 5
    response = tools.execute_tool({'tool_name':'search_inquiry_history', 'arguments':{'employee_id':'B001'}})
    assert response['error']['code'] == 'INVALID_ARGUMENTS'
    response = tools.execute_tool({'tool_name':'get_leave_status', 'arguments':{'as_of':'2026-11-04'}})
    assert response['data']['employee_id'] == 'A001'


def test_rag_bad_input_needs_no_model_or_database():
    from employee_tools.rag_search_tool import RegulationSearch
    rag = RegulationSearch('missing-rag-data')
    assert rag.search_regulations(' ')['status'] == 'error'
    assert rag.search_regulations('휴가', top_k=True)['status'] == 'error'
    assert rag.search_regulations('휴가')['error']['code'] == 'RAG_DB_NOT_FOUND'


def test_near_distance_provided_meals_need_review(context):
    trip = domestic(end_date="2026-11-04", distance_km=20, meal_days=0)
    assert calculate_travel_expense(trip, context=context)["status"] == "needs_review"
