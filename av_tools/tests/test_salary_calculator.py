# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from av_tools.av_tools.page.salary_calculator.salary_calculator import (
	_assignment_fields,
	_assignment_values,
	_fallback_calc,
	_make_proposed_slip,
	_solve_via_hrms,
	create_salary_structure_assignment,
	get_salary_slip_preview,
	get_salary_structure_components,
	run_calculation,
)

COMPANY = "_Test Company"
STRUCTURE = "AV Test Calculator Structure"


class PreviewAssignment(frappe._dict):
	def as_dict(self):
		return dict(self)

	def get_evaluated_components(self):
		return {
			"earnings": [
				frappe._dict(default_amount=self.base, statistical_component=0, do_not_include_in_total=0)
			]
		}


class PreviewSlip(frappe._dict):
	def __init__(self, assignment):
		super().__init__(
			currency="TZS",
			_salary_structure_assignment=frappe._dict(assignment),
			_ssa_doc=assignment,
			_evaluated_components=assignment.get_evaluated_components(),
		)

	def _get_ssa_doc(self):
		return self._ssa_doc

	def set(self, field, value):
		self[field] = value

	def process_salary_structure(self, for_preview):
		# At full payment days HRMS uses the assignment default amount for Basic.
		self.gross_pay = self._evaluated_components["earnings"][0].default_amount
		nssf = self.gross_pay * 0.10
		nhif = self._salary_structure_assignment.base * 0.03
		paye = 128_000 + (self.gross_pay - nssf - 1_000_000) * 0.30
		self.total_deduction = nssf + nhif + paye
		self.net_pay = self.gross_pay - self.total_deduction


class TestSalaryCalculatorTarget(TestCase):
	def test_employee_target_recalculates_assignment_default_amounts(self):
		assignment = PreviewAssignment(base=3_500_000)
		with (
			patch("frappe.get_doc", side_effect=PreviewAssignment),
			patch(
				"hrms.payroll.doctype.salary_structure.salary_structure.make_salary_slip",
				side_effect=lambda *args, **kwargs: PreviewSlip(assignment),
			),
		):
			result = _solve_via_hrms(STRUCTURE, "EMP-1", "net_pay", 4_500_000, precision=0)

		self.assertEqual(result["net_pay"], 4_500_000)
		self.assertEqual(result["gross_pay"], result["base"])
		self.assertAlmostEqual(result["base"], 7_213_333, delta=1)
		self.assertEqual(assignment.base, 3_500_000)


class TestSalaryCalculatorAssignmentInputs(TestCase):
	def test_controls_follow_structure_formulas_and_field_permissions(self):
		structure = frappe._dict(
			earnings=[frappe._dict(formula="base + duty", condition="")],
			deductions=[frappe._dict(formula="gross_pay * 0.15", condition="heslb and protected_flag")],
		)
		meta = Mock()
		meta.fields = [
			frappe._dict(fieldname=name, label=name, fieldtype=fieldtype)
			for name, fieldtype in (
				("base", "Currency"), ("duty", "Currency"), ("transport", "Currency"),
				("heslb", "Check"), ("protected_flag", "Check"),
			)
		]
		meta.get_permitted_fieldnames.side_effect = [
			["base", "duty", "transport", "heslb", "protected_flag"],
			["base", "duty", "transport", "heslb"],
		]
		with patch("frappe.get_meta", return_value=meta):
			fields = _assignment_fields(structure)

		self.assertEqual(set(fields), {"duty", "heslb"})
		source = frappe._dict(duty=100000, heslb=1)
		self.assertEqual(
			_assignment_values(fields, source, {"heslb": 0}),
			{"duty": 100000, "heslb": 0},
		)
		with self.assertRaises(frappe.ValidationError):
			_assignment_values(fields, source, {"transport": 1})

	def test_proposed_values_reach_hrms_before_evaluation(self):
		assignment = PreviewAssignment(
			base=0, duty=150000, transport=80000, heslb=0,
			salary_structure=STRUCTURE, employee="EMP-1", from_date="2026-12-01",
		)
		slip = Mock()
		slip.run_method.side_effect = lambda *args, **kwargs: self.assertEqual(
			slip._salary_structure_assignment,
			{**assignment, "base": 1000000},
		)

		def map_slip(*args, postprocess, **kwargs):
			postprocess(None, slip)
			return slip

		with patch("frappe.model.mapper.get_mapped_doc", side_effect=map_slip):
			self.assertIs(_make_proposed_slip(assignment, 1000000), slip)
		self.assertIs(slip._ssa_doc, assignment)
		self.assertEqual(slip.gross_pay, 1000000)
		slip.run_method.assert_called_once_with("process_salary_structure", for_preview=1)


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
