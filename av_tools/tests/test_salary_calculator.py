# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from av_tools.av_tools.page.salary_calculator.salary_calculator import (
	_fallback_calc,
	create_salary_structure_assignment,
	get_salary_slip_preview,
	get_salary_structure_components,
	run_calculation,
)

COMPANY = "_Test Company"
STRUCTURE = "AV Test Calculator Structure"


class TestSalaryCalculator(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from hrms.payroll.doctype.salary_structure.test_salary_structure import make_salary_structure

		cls.structure = make_salary_structure(
			STRUCTURE,
			"Monthly",
			company=COMPANY,
			currency=frappe.get_cached_value("Company", COMPANY, "default_currency"),
			dont_submit=False,
		)

	def test_components_serialized(self):
		result = get_salary_structure_components(STRUCTURE)
		self.assertTrue(result["earnings"])
		self.assertTrue(result["deductions"])
		self.assertEqual(result["earnings"][0]["key"], "E-0")
		self.assertIn("formula", result["earnings"][0])

	def test_fallback_calculation_hits_target(self):
		components = get_salary_structure_components(STRUCTURE)
		selected = [c["salary_component"] for c in components["earnings"] + components["deductions"]]
		result = run_calculation(
			STRUCTURE, "Gross Pay", gross_pay=50000, selected_components=frappe.as_json(selected)
		)
		self.assertGreater(result["base"], 0)
		self.assertAlmostEqual(result["gross_pay"], 50000, delta=1)
		self.assertEqual(run_calculation(STRUCTURE, "Net Pay", net_pay=0)["base"], 0)
		net = run_calculation(STRUCTURE, "Net Pay", net_pay=30000, selected_components=selected)
		self.assertAlmostEqual(net["net_pay"], 30000, delta=1)

	def test_fallback_calc_precision(self):
		structure = frappe.get_cached_doc("Salary Structure", STRUCTURE)
		result = _fallback_calc(structure, 1000, 2, [r.salary_component for r in structure.earnings], {})
		self.assertEqual(result["base"], 1000)
		self.assertGreaterEqual(result["gross_pay"], 0)

	def test_preview_renders(self):
		html = get_salary_slip_preview(
			STRUCTURE,
			1000,
			1200,
			1000,
			[{"salary_component": "Basic Salary", "amount": 1000}],
			[{"salary_component": "Professional Tax", "amount": 200}],
		)
		self.assertIn("1,200", html)
		self.assertIn(STRUCTURE, html)

	def test_assignment_creation_and_duplicate_guard(self):
		from erpnext.setup.doctype.employee.test_employee import make_employee

		employee = make_employee("av_calc_employee@example.com", company=COMPANY)
		name = create_salary_structure_assignment(employee, STRUCTURE, nowdate(), base=5000)
		self.assertEqual(frappe.db.get_value("Salary Structure Assignment", name, "docstatus"), 1)
		self.assertRaises(
			frappe.ValidationError, create_salary_structure_assignment, employee, STRUCTURE, nowdate(), 5000
		)
		result = run_calculation(STRUCTURE, "Gross Pay", gross_pay=20000, employee=employee)
		self.assertIn("gross_pay", result)
