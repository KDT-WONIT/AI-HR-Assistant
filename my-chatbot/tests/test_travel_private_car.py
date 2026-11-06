import unittest

from app.agent.travel_estimate_answers import apply_defaults, relax_for_estimate
from app.vendor.employee_tools.travel_expense_tool import calculate_travel_expense
from app.vendor.employee_tools.common import EmployeeContext


class PrivateCarEstimateTests(unittest.TestCase):
    def base(self, **extra):
        return dict(trip_type='domestic', destination_city='서울', start_date='2026-11-10', end_date='2026-11-10',
                    transport_mode='private_car', **extra)

    def test_long_distance_private_car_is_estimated_not_blocked(self):
        trip, notes = apply_defaults(self.base())
        self.assertEqual(trip['transport_mode'], 'public_transport')  # 담당자 확인 분기를 피해 일반 계산으로
        self.assertEqual(trip['transport_cost_krw'], 15000)   # 100km 기본 가정 × 150원
        self.assertEqual(trip['toll_cost_krw'], 5000)
        self.assertTrue(any('연료비' in note for note in notes))
        self.assertTrue(any('통행료' in note for note in notes))

    def test_user_entered_costs_are_kept(self):
        trip, _ = apply_defaults(self.base(distance_km=300, same_city=False, transport_cost_krw=70000, toll_cost_krw=20000))
        self.assertEqual((trip['transport_cost_krw'], trip['toll_cost_krw']), (70000, 20000))

    def test_near_distance_keeps_flat_allowance_path(self):
        trip, _ = apply_defaults(self.base(distance_km=20, same_city=True))
        self.assertEqual(trip['transport_mode'], 'private_car')
        self.assertNotIn('transport_cost_krw', trip)

    def test_other_transport_unchanged(self):
        trip, _ = apply_defaults(dict(self.base(), transport_mode='public_transport'))
        self.assertNotIn('toll_cost_krw', trip)

    def calc(self, trip):
        context = EmployeeContext('E1', {'travel_grade': 'grade_3'}, None)
        result = calculate_travel_expense(trip, context=context)
        if result['status'] == 'needs_review':
            relaxed = relax_for_estimate(trip)
            self.assertIsNotNone(relaxed)
            result = calculate_travel_expense(relaxed[0], context=context)
        return result

    def test_every_vehicle_produces_a_total(self):
        for mode in ('private_car', 'company_car', 'rental_car', 'public_transport'):
            trip, _ = apply_defaults(dict(self.base(), transport_mode=mode, end_date='2026-11-12'))
            result = self.calc(trip)
            self.assertEqual(result['status'], 'success', mode)
            self.assertIsNotNone(result['data']['estimated_total_krw'], mode)

    def test_near_distance_review_cases_are_relaxed(self):
        trip, _ = apply_defaults(dict(self.base(distance_km=20, same_city=True), transport_mode='company_car'))
        result = self.calc(trip)
        self.assertEqual(result['status'], 'success')

    def test_overseas_gets_estimated_fare_and_rate(self):
        for mode in ('public_transport', 'private_car', 'rental_car'):
            trip, notes = apply_defaults(dict(trip_type='overseas', destination_city='도쿄', destination_country='일본',
                                              start_date='2026-11-18', end_date='2026-11-19', transport_mode=mode))
            result = self.calc(trip)
            self.assertEqual(result['status'], 'success', mode)
            self.assertTrue(any('환율' in note for note in notes))


if __name__ == '__main__':
    unittest.main()
