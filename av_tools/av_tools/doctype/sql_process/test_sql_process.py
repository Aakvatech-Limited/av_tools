# Copyright (c) 2022, Aakvatech and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSQLProcess(FrappeTestCase):
	def test_process_listing_is_disabled(self):
		doc = frappe.get_doc("SQL Process")
		with self.assertRaises(frappe.PermissionError):
			doc.get_process()

	def test_process_termination_is_disabled(self):
		doc = frappe.get_doc("SQL Process")
		with self.assertRaises(frappe.PermissionError):
			doc.kill_process("123")
