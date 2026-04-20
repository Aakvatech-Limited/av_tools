# Copyright (c) 2022, Aakvatech and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestReportingCurrencySettings(FrappeTestCase):
	def test_doctype_can_be_instantiated(self):
		doc = frappe.new_doc("Reporting Currency Settings")

		self.assertEqual(doc.doctype, "Reporting Currency Settings")
