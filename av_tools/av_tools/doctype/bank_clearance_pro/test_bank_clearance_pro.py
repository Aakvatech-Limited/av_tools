# -*- coding: utf-8 -*-
# Copyright (c) 2020, Aakvatech and Contributors
# See license.txt
from __future__ import unicode_literals

import frappe
from frappe.tests.utils import FrappeTestCase


class TestBankClearancePro(FrappeTestCase):
	def test_get_payment_entries_requires_dates_and_account(self):
		doc = frappe.new_doc("Bank Clearance Pro")

		with self.assertRaises(frappe.ValidationError):
			doc.get_payment_entries()
