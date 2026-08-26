# Copyright (c) 2020, Aakvatech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestBankClearancePro(IntegrationTestCase):
	def test_get_payment_entries_requires_dates_and_account(self):
		doc = frappe.new_doc("Bank Clearance Pro")

		with self.assertRaises(frappe.ValidationError):
			doc.get_payment_entries()
