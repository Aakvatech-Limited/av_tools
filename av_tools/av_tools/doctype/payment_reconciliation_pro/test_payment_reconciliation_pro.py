# Copyright (c) 2020, Aakvatech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestPaymentReconciliationPro(IntegrationTestCase):
	def test_check_mandatory_to_fetch_requires_core_filters(self):
		doc = frappe.new_doc("Payment Reconciliation Pro")

		with self.assertRaises(frappe.ValidationError):
			doc.check_mandatory_to_fetch()
