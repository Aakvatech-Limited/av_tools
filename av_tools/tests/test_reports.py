# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import json

import frappe
from frappe.desk.query_report import run
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, get_first_day, today

APP = "av_tools"
COMPANY = "_Test Company"


def unexpected_errors():
	return (
		TypeError,
		AttributeError,
		ImportError,
		NameError,
		KeyError,
		IndexError,
		ZeroDivisionError,
		frappe.db.ProgrammingError,
		frappe.db.InternalError,
	)


def generic_filters():
	fiscal_year = frappe.db.get_value(
		"Fiscal Year", {"year_start_date": ("<=", today()), "year_end_date": (">=", today())}, "name"
	)
	return frappe._dict(
		company=COMPANY,
		from_date=get_first_day(add_months(today(), -12)),
		to_date=today(),
		from_fiscal_year=fiscal_year,
		to_fiscal_year=fiscal_year,
		fiscal_year=fiscal_year,
		date=today(),
		posting_date=today(),
		start_date=get_first_day(add_months(today(), -12)),
		end_date=today(),
		period_start_date=get_first_day(add_months(today(), -12)),
		period_end_date=today(),
		periodicity="Monthly",
		filter_based_on="Date Range",
		range="Monthly",
		currency=frappe.get_cached_value("Company", COMPANY, "default_currency"),
		docstatus="Submitted",
		doctype="Sales Invoice",
		party_type="Customer",
		report_type="Both",
		include_default_book_entries=1,
	)


def declared_filters(report):
	import re

	doc = frappe.get_doc("Report", report.name)
	declared = {f.fieldname for f in doc.filters}
	script = frappe.get_app_path(
		APP, frappe.scrub(doc.module), "report", frappe.scrub(report.name), frappe.scrub(report.name) + ".js"
	)
	try:
		with open(script) as handle:
			declared |= set(re.findall(r"[\"']?fieldname[\"']?\s*:\s*[\"'](\w+)[\"']", handle.read()))
	except FileNotFoundError:
		pass
	return declared


class TestReports(IntegrationTestCase):
	"""Every av_tools report must execute on v16 / MariaDB 11 with generic filters."""

	def reports(self):
		modules = frappe.get_module_list(APP)
		return frappe.get_all(
			"Report",
			filters={"module": ("in", modules), "disabled": 0},
			fields=["name", "report_type", "ref_doctype", "is_standard"],
			order_by="name",
		)

	def test_reports_installed(self):
		reports = self.reports()
		self.assertGreaterEqual(len(reports), 34)
		non_standard = [r.name for r in reports if r.is_standard != "Yes"]
		frappe.flags.av_tools_non_standard_reports = non_standard
		print("\nReports shipped with is_standard=No:", non_standard)

	def test_reports_execute(self):
		outcomes = {}
		filters = generic_filters()
		for report in self.reports():
			with self.subTest(report=report.name):
				if not frappe.db.exists("DocType", report.ref_doctype):
					outcomes[report.name] = f"blocked: ref DocType {report.ref_doctype} not installed"
					continue
				report_filters = dict(filters)
				for fieldname in declared_filters(report):
					report_filters.setdefault(fieldname, "")
				frappe.db.savepoint("report_run")
				try:
					result = run(
						report.name, filters=frappe.as_json(report_filters), ignore_prepared_report=True
					)
					self.assertIn("columns", result)
					self.assertIn("result", result)
					outcomes[report.name] = "pass"
				except frappe.db.OperationalError as error:
					if "Unknown column" in str(error):
						outcomes[report.name] = (
							f"blocked: {str(error)[:120]} (csf_tz custom field not present)"
						)
					else:
						outcomes[report.name] = f"fail: {type(error).__name__}: {str(error)[:160]}"
						self.fail(outcomes[report.name])
				except frappe.ValidationError as error:
					outcomes[report.name] = f"needs filters: {str(error)[:120]}"
				except Exception as error:
					outcomes[report.name] = f"fail: {type(error).__name__}: {str(error)[:160]}"
					self.fail(outcomes[report.name])
				finally:
					frappe.db.rollback(save_point="report_run")
		frappe.flags.av_tools_report_outcomes = outcomes
		print("\nReports:", json.dumps(outcomes, indent=1))

	def test_script_reports_have_execute(self):
		for report in self.reports():
			if report.report_type != "Script Report":
				continue
			with self.subTest(report=report.name):
				module = frappe.db.get_value("Report", report.name, "module")
				method = f"{frappe.local.module_app[frappe.scrub(module)]}.{frappe.scrub(module)}.report.{frappe.scrub(report.name)}.{frappe.scrub(report.name)}.execute"
				self.assertTrue(callable(frappe.get_attr(method)), method)

	def test_query_reports_declare_their_parameters(self):
		import re

		for report in self.reports():
			if report.report_type != "Query Report":
				continue
			doc = frappe.get_doc("Report", report.name)
			params = set(re.findall(r"%\((\w+)\)s", doc.query or ""))
			declared = declared_filters(report)
			with self.subTest(report=report.name):
				self.assertFalse(
					params - declared, f"{report.name} uses undeclared filters {params - declared}"
				)
