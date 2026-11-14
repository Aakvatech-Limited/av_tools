"""Unit coverage for fixed 30-day salary proration (no database required)."""

import unittest

from av_tools.payroll.fixed_30_days import fixed_30_payment_days


class TestFixedThirtyDayPayroll(unittest.TestCase):
    def check(self, expected, actual_days, working_days, start, end, eligible_start=None, eligible_end=None):
        self.assertAlmostEqual(
            fixed_30_payment_days(
                actual_days, working_days, start, end,
                eligible_start or start, eligible_end or end
            ),
            expected,
        )

    def test_full_february_non_leap(self):
        self.check(30, 28, 28, "2026-02-01", "2026-02-28")

    def test_full_february_leap(self):
        self.check(30, 29, 29, "2028-02-01", "2028-02-29")

    def test_full_30_day_month(self):
        self.check(30, 30, 30, "2026-04-01", "2026-04-30")

    def test_full_31_day_month(self):
        self.check(30, 31, 31, "2026-07-01", "2026-07-31")

    def test_31_day_month_unpaid_day(self):
        self.check(29, 30, 31, "2026-07-01", "2026-07-31")

    def test_february_three_unpaid_days(self):
        self.check(27, 25, 28, "2026-02-01", "2026-02-28")

    def test_half_day_unpaid(self):
        self.check(29.5, 27.5, 28, "2026-02-01", "2026-02-28")

    def test_paid_holidays_excluded_upstream(self):
        self.check(30, 22, 22, "2026-07-01", "2026-07-31")

    def test_partial_february_joining(self):
        self.check(9, 9, 28, "2026-02-01", "2026-02-28", "2026-02-20", "2026-02-28")

    def test_partial_31_day_month_relieving(self):
        self.check(15, 15, 31, "2026-07-01", "2026-07-31", "2026-07-01", "2026-07-15")

    def test_partial_pay_period(self):
        self.check(12, 12, 12, "2026-07-10", "2026-07-21")

    def test_no_negative_salary_days(self):
        self.check(0, -1, 28, "2026-02-01", "2026-02-28")

    def test_partial_period_capped(self):
        self.check(30, 31, 31, "2026-07-01", "2026-07-30")


    def test_february_2027_all_28_days_unpaid_zero_pay(self):
        self.check(0, 0, 28, "2027-02-01", "2027-02-28")

    def test_february_2027_27_days_unpaid_deduction_mode(self):
        self.check(3, 1, 28, "2027-02-01", "2027-02-28")

    def test_february_2027_27_days_unpaid_attendance_mode(self):
        self.assertEqual(
            fixed_30_payment_days(1, 28, "2027-02-01", "2027-02-28",
                                  "2027-02-01", "2027-02-28", mode="Attendance"),
            1,
        )

    def test_attendance_mode_full_february_paid_in_full(self):
        self.assertEqual(
            fixed_30_payment_days(28, 28, "2027-02-01", "2027-02-28",
                                  "2027-02-01", "2027-02-28", mode="Attendance"),
            30,
        )

    def test_auto_below_crossover_uses_deduction_mode(self):
        self.assertEqual(
            fixed_30_payment_days(14, 28, "2027-02-01", "2027-02-28",
                                  "2027-02-01", "2027-02-28",
                                  mode="Automatic", crossover_days=15),
            16,
        )

    def test_auto_at_crossover_uses_attendance_mode(self):
        self.assertEqual(
            fixed_30_payment_days(13, 28, "2027-02-01", "2027-02-28",
                                  "2027-02-01", "2027-02-28",
                                  mode="Automatic", crossover_days=15),
            13,
        )

    def test_zero_pay_in_31_day_month(self):
        self.check(0, 0, 31, "2027-07-01", "2027-07-31")

    def test_attendance_mode_zero_pay_in_leap_february(self):
        self.assertEqual(
            fixed_30_payment_days(0, 29, "2028-02-01", "2028-02-29",
                                  "2028-02-01", "2028-02-29", mode="Attendance"),
            0,
        )

    def test_full_month_with_holidays_excluded_and_no_attendance(self):
        self.check(0, 0, 22, "2027-02-01", "2027-02-28")

    def test_one_unpaid_february_deduction_vs_attendance(self):
        args = (27, 28, "2027-02-01", "2027-02-28",
                "2027-02-01", "2027-02-28")
        self.assertEqual(fixed_30_payment_days(*args, mode="Deduction"), 29)
        self.assertEqual(fixed_30_payment_days(*args, mode="Attendance"), 27)


if __name__ == "__main__":
    unittest.main()
