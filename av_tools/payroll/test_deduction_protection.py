"""Basic capacity allocator regression tests; run with Frappe test runner."""

import unittest

from av_tools.payroll.deduction_protection import allocate_capacity


class TestPayrollDeductionProtection(unittest.TestCase):
    def test_normal_salary_recovers_all(self):
        self.assertEqual(allocate_capacity(900000, 150000, 300000, [200000, 100000], [95000]), ([200000, 100000], [95000]))

    def test_low_pay_current_first_then_arrears(self):
        self.assertEqual(allocate_capacity(300000, 75000, 100000, [200000, 100000], [95000]), ([125000, 0], [0]))

    def test_no_eligible_capacity(self):
        self.assertEqual(allocate_capacity(100000, 100000, 30000, [200000], [95000]), ([0], [0]))

    def test_fractional_allocation(self):
        self.assertEqual(allocate_capacity(100, 20, 30, [40, 20], [20]), ([40, 10], [0]))

    def test_prior_arrears_fifo_with_remaining_capacity(self):
        self.assertEqual(allocate_capacity(500, 100, 100, [100], [120, 90, 80]), ([100], [120, 80, 0]))

    def test_negative_capacity_never_generates_negative_recovery(self):
        self.assertEqual(allocate_capacity(50, 75, 20, [100], [50]), ([0], [0]))
