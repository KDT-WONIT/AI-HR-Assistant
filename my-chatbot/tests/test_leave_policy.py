import unittest
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from app.integrations.leave_policy import annual_days, leave_entitlement, mandatory_use_days
from app.schemas import ToolInput, UserProfile
from app.tools.execution import business_data


class LeavePolicyTests(unittest.TestCase):
    def test_annual_days_follow_work_rules_article_20(self):
        self.assertEqual([annual_days(n) for n in (1, 2, 3, 4, 5, 11, 13, 21, 30)], [15, 15, 16, 16, 17, 20, 21, 25, 25])

    def test_first_year_accrues_one_day_per_full_month_up_to_eleven(self):
        result = leave_entitlement(date(2026, 3, 10), date(2026, 11, 4))
        self.assertEqual((result['kind'], result['granted_days']), ('first_year', 7))
        self.assertEqual(result['period_end'], '2027-03-09')
        self.assertEqual(leave_entitlement(date(2025, 11, 5), date(2026, 11, 4))['granted_days'], 11)

    def test_period_runs_from_last_anniversary_to_the_day_before_next(self):
        result = leave_entitlement(date(2015, 3, 10), date(2026, 11, 4), '2직급')
        self.assertEqual((result['granted_days'], result['period_start'], result['period_end']), (20, '2026-03-10', '2027-03-09'))
        self.assertEqual(result['mandatory_use_days'], 25)
        self.assertEqual(result['next_anniversary_days'], 20)

    def test_mandatory_use_days_by_grade_and_leap_day_hire(self):
        self.assertEqual([mandatory_use_days(g) for g in ('2직급', '3직급', '4직급', None)], [25, 24, 24, None])
        self.assertEqual(leave_entitlement(date(2020, 2, 29), date(2026, 2, 28))['completed_years'], 6)
        self.assertIsNone(leave_entitlement(date(2030, 1, 1), date(2026, 1, 1)))

    def test_business_data_uses_profile_when_no_leave_records_exist(self):
        profile = UserProfile(employee_id='A', name='가', grade='3직급', hired_at=date(2019, 5, 1))
        request = ToolInput(question='내 연차는 며칠이야?', employee_id='A', conversation_id=uuid4(), user_profile=profile)
        with patch('app.tools.execution.connection_scope') as scope:
            scope.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            data, missing = business_data('work_labor', request)
        self.assertIsNone(missing)
        self.assertGreater(data['leave_entitlement']['granted_days'], 14)
        self.assertEqual(data['leave_entitlement']['mandatory_use_days'], 24)
        request.arguments = {'requested_days': 3}
        with patch('app.tools.execution.connection_scope') as scope:
            scope.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            data, _ = business_data('work_labor', request)
        self.assertTrue(data['leave_projection']['used_unknown'])
