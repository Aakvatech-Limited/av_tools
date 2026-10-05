from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools_hooks.stock_entry import set_bom_guided_qty


class TestStockEntryBomGuidedQty(FrappeTestCase):
	def test_sets_scaled_bom_qty_without_changing_actual_qty(self):
		doc = frappe._dict(
			{
				"bom_no": "BOM-TEST-001",
				"company": "Test Company",
				"fg_completed_qty": 10,
				"use_multi_level_bom": 0,
				"items": [
					frappe._dict(
						{
							"item_code": "RM-001",
							"qty": 12,
							"is_finished_item": 0,
							"is_scrap_item": 0,
						}
					),
					frappe._dict(
						{
							"item_code": "FG-001",
							"qty": 10,
							"is_finished_item": 1,
							"is_scrap_item": 0,
						}
					),
				],
			}
		)

		raw = {"RM-001": frappe._dict({"item_code": "RM-001", "qty": 15})}

		with patch(
			"av_tools.av_tools_hooks.stock_entry.get_bom_items_as_dict",
			side_effect=[raw, {}],
		):
			set_bom_guided_qty(doc)

		self.assertEqual(doc.items[0].bom_guided_qty, 15)
		self.assertEqual(doc.items[0].qty, 12)
		self.assertEqual(doc.items[1].bom_guided_qty, 10)

	def test_uses_original_item_for_alternative_material(self):
		doc = frappe._dict(
			{
				"bom_no": "BOM-TEST-001",
				"company": "Test Company",
				"fg_completed_qty": 5,
				"use_multi_level_bom": 0,
				"items": [
					frappe._dict(
						{
							"item_code": "ALT-RM-001",
							"original_item": "RM-001",
							"qty": 4,
							"is_finished_item": 0,
							"is_scrap_item": 0,
						}
					)
				],
			}
		)

		raw = {"RM-001": frappe._dict({"item_code": "RM-001", "qty": 7.5})}

		with patch(
			"av_tools.av_tools_hooks.stock_entry.get_bom_items_as_dict",
			side_effect=[raw, {}],
		):
			set_bom_guided_qty(doc)

		self.assertEqual(doc.items[0].bom_guided_qty, 7.5)
		self.assertEqual(doc.items[0].qty, 4)

	def test_clears_guided_qty_without_bom(self):
		doc = frappe._dict(
			{
				"bom_no": None,
				"fg_completed_qty": 0,
				"items": [frappe._dict({"bom_guided_qty": 9, "qty": 8})],
			}
		)

		set_bom_guided_qty(doc)

		self.assertIsNone(doc.items[0].bom_guided_qty)
		self.assertEqual(doc.items[0].qty, 8)
