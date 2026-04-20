# -*- coding: utf-8 -*-
# Copyright (c) 2020, Aakvatech and Contributors
# See license.txt
from __future__ import unicode_literals

import frappe
from frappe.tests.utils import FrappeTestCase


class TestPaymentReconciliationPro(FrappeTestCase):
	def test_check_mandatory_to_fetch_requires_core_filters(self):
		doc = frappe.new_doc("Payment Reconciliation Pro")

		with self.assertRaises(frappe.ValidationError):
			doc.check_mandatory_to_fetch()
