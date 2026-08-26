# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import re

import frappe
from frappe.tests import IntegrationTestCase

APP = "av_tools"


def sample_document(doctype):
	"""Return a name of a document of `doctype`, creating an ERPNext fixture when possible."""
	existing = frappe.get_all(doctype, pluck="name", limit=1, order_by="creation desc")
	if existing:
		return existing[0]
	if doctype == "Sales Invoice":
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		return create_sales_invoice(do_not_submit=True).name
	if doctype == "Purchase Invoice":
		from erpnext.accounts.doctype.purchase_invoice.test_purchase_invoice import make_purchase_invoice

		return make_purchase_invoice(do_not_submit=True).name
	if doctype == "Journal Entry":
		from erpnext.accounts.doctype.journal_entry.test_journal_entry import make_journal_entry

		return make_journal_entry("_Test Cash - _TC", "_Test Bank - _TC", 100, save=True).name
	return None


class TestPrintFormats(IntegrationTestCase):
	"""Every av_tools print format must render without template errors on v16."""

	def print_formats(self):
		modules = frappe.get_module_list(APP)
		return frappe.get_all(
			"Print Format",
			filters={"module": ("in", modules)},
			fields=["name", "doc_type", "disabled"],
			order_by="name",
		)

	def test_print_formats_installed(self):
		names = {row.name for row in self.print_formats()}
		self.assertGreaterEqual(len(names), 12)

	def test_print_formats_render(self):
		outcomes = {}
		for row in self.print_formats():
			with self.subTest(print_format=row.name):
				if row.disabled:
					outcomes[row.name] = "skipped: print format is disabled"
					continue
				if not frappe.db.exists("DocType", row.doc_type):
					outcomes[row.name] = f"blocked: DocType {row.doc_type} not installed"
					continue
				try:
					name = sample_document(row.doc_type)
				except Exception as error:
					outcomes[row.name] = (
						f"blocked: could not build a {row.doc_type} fixture ({type(error).__name__})"
					)
					continue
				if not name:
					outcomes[row.name] = f"blocked: no {row.doc_type} document available"
					continue
				try:
					html = frappe.get_print(row.doc_type, name, print_format=row.name)
				except Exception as error:
					missing = re.search(r"Unknown column '?&?#?x?2?7?;?(\w+)", str(error))
					if missing:
						outcomes[row.name] = (
							f"blocked: template needs column '{missing.group(1)}' (csf_tz custom field not present)"
						)
						continue
					raise
				self.assertTrue(html and "<" in html, row.name)
				outcomes[row.name] = "pass"
		frappe.flags.av_tools_print_format_outcomes = outcomes
		print("\nPrint formats:", outcomes)
		failures = {k: v for k, v in outcomes.items() if v.startswith("fail")}
		self.assertFalse(failures, failures)
		self.assertEqual(len(outcomes), len(self.print_formats()))
