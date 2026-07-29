# -*- coding: utf-8 -*-
# Copyright (c) 2020, Aakvatech and Contributors
# See license.txt
from __future__ import unicode_literals

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools.doctype.special_closing_balance.special_closing_balance import get_items


class TestSpecialClosingBalance(FrappeTestCase):
	def test_get_items_returns_warehouse_stock_rows(self):
		with patch(
			"av_tools.av_tools.doctype.special_closing_balance.special_closing_balance.frappe.db.get_value",
			side_effect=[(1, 2), 0],
		), patch(
			"av_tools.av_tools.doctype.special_closing_balance.special_closing_balance.frappe.db.sql",
			return_value=[["ITEM-001", "Test Item", "Nos", "Main Stores - A"]],
		), patch(
			"av_tools.av_tools.doctype.special_closing_balance.special_closing_balance.get_stock_balance",
			return_value=(5, 12),
		):
			rows = get_items("Main Stores - A", "2026-03-10", "08:00:00", "Rubis Technical Services Limited")

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item"], "ITEM-001")
		self.assertEqual(rows[0]["quantity"], 5)
		self.assertEqual(rows[0]["valuation_rate"], 12)
