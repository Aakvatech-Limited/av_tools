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

	def test_guidance_uses_stock_uom_and_keeps_transaction_uom(self):
		doc = frappe._dict({
			"bom_no": "BOM-TEST-001", "company": "Test Company",
			"fg_completed_qty": 10, "use_multi_level_bom": 0,
			"items": [
				frappe._dict({"idx": 1, "item_code": "RM-001", "qty": 22, "transfer_qty": 550,
					"conversion_factor": 25, "is_finished_item": 0, "is_scrap_item": 0}),
				frappe._dict({"idx": 2, "item_code": "FG-001", "qty": 10, "transfer_qty": 10,
					"conversion_factor": 1, "is_finished_item": 1, "is_scrap_item": 0}),
				frappe._dict({"idx": 3, "item_code": "SCR-001", "qty": 3, "transfer_qty": 3,
					"conversion_factor": 1, "is_finished_item": 0, "is_scrap_item": 1}),
			]
		})
		raw = {"RM-001": frappe._dict({"item_code": "RM-001", "qty": 500})}
		scrap = {"SCR-001": frappe._dict({"item_code": "SCR-001", "qty": 2})}
		with patch(
			"av_tools.av_tools_hooks.stock_entry.get_bom_items_as_dict",
			side_effect=[raw, scrap],
		) as get_items:
			set_bom_guided_qty(doc)
			self.assertTrue(all(call.kwargs["fetch_qty_in_stock_uom"] for call in get_items.call_args_list))
		self.assertEqual(doc.items[0].bom_guided_qty, 20)
		self.assertEqual(doc.items[0].bom_guided_stock_qty, 500)
		self.assertEqual(doc.items[0].qty, 22)
		self.assertEqual(doc.items[0].transfer_qty, 550)
		self.assertEqual(doc.items[1].bom_guided_stock_qty, 10)
		self.assertEqual(doc.items[2].bom_guided_stock_qty, 2)
