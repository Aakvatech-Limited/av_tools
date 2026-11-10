"""Connections metadata and existing-request backfill; synthetic records only."""

import ast
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from av_tools.asset_reconciliation.dashboard import purchase_invoice as asset_connections
from av_tools.tax_detail_rebuild.connections import (
	ENTRY,
	LINK_FIELDS,
	TARGET,
	purchase_invoice,
	reference_fields,
	sales_invoice,
)

ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
	__getattr__ = dict.get


class TestConnections(unittest.TestCase):
	def test_both_dashboards_use_distinct_typed_child_fields(self):
		for source, hook in (("Sales Invoice", sales_invoice), ("Purchase Invoice", purchase_invoice)):
			with self.subTest(source=source):
				result = hook({})
				self.assertEqual(result["non_standard_fieldnames"][TARGET], LINK_FIELDS[source])
				groups = [group for group in result["transactions"] if TARGET in group["items"]]
				self.assertEqual(len(groups), 1)
				self.assertEqual(groups[0]["fieldnames"][TARGET], LINK_FIELDS[source])

	def test_preserves_asset_and_core_connections_without_mutating_or_duplicates(self):
		original = {
			"transactions": [{"label": "Payment", "items": ["Payment Entry"]}],
			"non_standard_fieldnames": {"Payment Entry": "reference_name"},
			"internal_links": {"Sales Order": ["items", "sales_order"]},
		}
		before = copy.deepcopy(original)
		result = purchase_invoice(asset_connections(original))
		self.assertEqual(original, before)
		self.assertEqual(result["internal_links"], original["internal_links"])
		self.assertEqual(result["non_standard_fieldnames"]["Payment Entry"], "reference_name")
		self.assertIn("Asset Capitalization Reconciliation", result["non_standard_fieldnames"])
		self.assertEqual(purchase_invoice(result), result)

	def test_corrects_existing_group_filter_without_duplicate_connection(self):
		original = {
			"transactions": [
				{"label": "Existing", "items": [TARGET], "fieldnames": {TARGET: "source_invoice"}}
			]
		}
		result = purchase_invoice(original)
		self.assertEqual(len(result["transactions"]), 1)
		self.assertEqual(result["transactions"][0]["fieldnames"][TARGET], "rebuild_purchase_invoice")
		self.assertEqual(original["transactions"][0]["fieldnames"][TARGET], "source_invoice")

	def test_same_named_sales_and_purchase_invoices_cannot_cross_link(self):
		name = "IDENTICAL-INVOICE-NAME"
		purchase = reference_fields("Purchase Invoice", name)
		sales = reference_fields("Sales Invoice", name)
		self.assertEqual(purchase, {"rebuild_purchase_invoice": name, "rebuild_sales_invoice": None})
		self.assertEqual(sales, {"rebuild_purchase_invoice": None, "rebuild_sales_invoice": name})
		self.assertTrue(all(value is None for value in reference_fields("Other", name).values()))

	def test_native_counter_fields_exist_only_on_child_table(self):
		base = ROOT / "av_tools" / "doctype"
		parent = json.loads(
			(base / "item_wise_tax_detail_rebuild/item_wise_tax_detail_rebuild.json").read_text()
		)
		child = json.loads(
			(base / "item_wise_tax_detail_rebuild_entry/item_wise_tax_detail_rebuild_entry.json").read_text()
		)
		parent_fields = {row["fieldname"]: row for row in parent["fields"]}
		child_fields = {row["fieldname"]: row for row in child["fields"]}
		self.assertEqual(parent_fields["entries"]["options"], ENTRY)
		for doctype, fieldname in LINK_FIELDS.items():
			self.assertNotIn(fieldname, parent_fields)
			self.assertEqual(child_fields[fieldname]["fieldtype"], "Link")
			self.assertEqual(child_fields[fieldname]["options"], doctype)
			self.assertEqual(child_fields[fieldname]["read_only"], 1)

	def test_hooks_extend_existing_purchase_override(self):
		tree = ast.parse((ROOT / "hooks.py").read_text())
		for node in tree.body:
			if isinstance(node, ast.Assign) and any(
				isinstance(t, ast.Name) and t.id == "override_doctype_dashboards" for t in node.targets
			):
				hooks = ast.literal_eval(node.value)
				self.assertIn(
					"av_tools.asset_reconciliation.dashboard.purchase_invoice", hooks["Purchase Invoice"]
				)
				self.assertIn(
					"av_tools.tax_detail_rebuild.connections.purchase_invoice", hooks["Purchase Invoice"]
				)
				self.assertEqual(
					hooks["Sales Invoice"], "av_tools.tax_detail_rebuild.connections.sales_invoice"
				)
				return
		self.fail("Dashboard hook mapping not found")

	def test_backfill_is_idempotent_and_touches_only_derived_child_links(self):
		rows = [
			Row(name="E1", parent="RUN1", source_doctype="Purchase Invoice", source_invoice="SAME"),
			Row(name="E2", parent="RUN2", source_doctype="Sales Invoice", source_invoice="SAME"),
			Row(name="E3", parent="RUN1", source_doctype=None, source_invoice="OTHER"),
		]
		f = ModuleType("frappe")
		f.db = Mock()
		f.db.exists.return_value = True
		f.db.get_value.return_value = "Purchase Invoice"
		f.get_all = Mock(return_value=rows)
		f.clear_cache = Mock()

		def update(doctype, name, values, update_modified):
			self.assertEqual(doctype, ENTRY)
			self.assertFalse(update_modified)
			self.assertEqual(set(values), set(LINK_FIELDS.values()))
			for row in rows:
				if row.name == name:
					row.update(values)

		f.db.set_value.side_effect = update
		spec = importlib.util.spec_from_file_location(
			"tax_connections_patch_test", ROOT / "patches/v1_0/backfill_item_tax_rebuild_connections.py"
		)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"frappe": f}):
			spec.loader.exec_module(module)
			module.execute()
			self.assertEqual(f.db.set_value.call_count, 3)
			module.execute()
			self.assertEqual(f.db.set_value.call_count, 3)
		self.assertEqual(rows[0].rebuild_purchase_invoice, "SAME")
		self.assertIsNone(rows[0].rebuild_sales_invoice)
		self.assertEqual(rows[1].rebuild_sales_invoice, "SAME")
		self.assertIsNone(rows[1].rebuild_purchase_invoice)
		self.assertEqual(rows[2].rebuild_purchase_invoice, "OTHER")
		self.assertEqual(
			f.get_all.call_args.kwargs["filters"], {"parenttype": TARGET, "parentfield": "entries"}
		)
		patches = (ROOT / "patches.txt").read_text()
		self.assertGreater(
			patches.index("av_tools.patches.v1_0.backfill_item_tax_rebuild_connections"),
			patches.index("[post_model_sync]"),
		)


if __name__ == "__main__":
	unittest.main()
