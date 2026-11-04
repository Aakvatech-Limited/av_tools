"""Synthetic 5,000-SKU read-budget tests; no wall-clock/production SLA is inferred."""

import unittest
from collections import Counter
from types import ModuleType
from unittest.mock import Mock, patch

from av_tools.selling_pricing_engine import test_dashboard as fixture
from av_tools.selling_pricing_engine.test_pricing import PREFIX, Row, load


class TestCatalogueScale(unittest.TestCase):
	setUp = fixture.TestPricingDashboard.setUp

	def data(self, count=5000):
		return [
			Row(name=f"SKU-{index:05}", item_group="GROUP", stock_uom="Nos", sales_uom="Nos")
			for index in range(count)
		]

	def test_five_thousand_skus_and_ten_thousand_price_rows_are_batched(self):
		items = self.data()
		prices = [
			Row(
				name=item.name + suffix,
				item_code=item.name,
				uom="Nos",
				currency="TZS",
				price_list_rate=100,
				valid_from="2026-01-01" if suffix == "-current" else "2020-01-01",
				valid_upto=None if suffix == "-current" else "2025-12-31",
			)
			for item in items
			for suffix in ("-current", "-old")
		]
		calls = Counter()

		def read(doctype, **kwargs):
			calls[doctype] += 1
			if doctype == "Item":
				return items[: kwargs.get("limit_page_length", 5001)]
			self.assertEqual(doctype, "Item Price")
			self.assertEqual(kwargs["filters"]["price_list"], "Retail")
			batch = set(kwargs["filters"]["item_code"][1])
			rows = [row for row in prices if row.item_code in batch]
			start, size = kwargs.get("limit_start", 0), kwargs["limit_page_length"]
			return rows[start : start + size]

		self.filters.item_group = "GROUP"
		self.frappe.get_list.side_effect = read
		counts = self.module.coverage(self.filters, Row(enable_phase_2=0))
		self.assertEqual(counts["Standard price"], 5000)
		self.assertEqual(sum(counts.values()), 5000)
		self.assertEqual(calls["Item"], 1)
		self.assertLessEqual(calls["Item Price"], 30)
		self.frappe.get_doc.assert_not_called()
		self.frappe.get_all.assert_not_called()

	def test_large_unscoped_catalogue_requires_item_group(self):
		self.frappe.get_list.return_value = self.data()
		with self.assertRaisesRegex(ValueError, "Select an Item Group"):
			self.scope.catalog(self.filters)

	def test_detail_pages_cover_all_five_thousand_without_silent_truncation(self):
		self.filters.item_group = "GROUP"
		self.frappe.get_list.return_value = self.data()
		names = []
		for page in range(1, 11):
			self.filters.page = page
			rows = self.scope.detail_items(self.filters)
			self.assertEqual(len(rows), 500)
			self.assertEqual(self.filters._scope_total, 5000)
			names.extend(row.name for row in rows)
		self.assertEqual(len(set(names)), 5000)
		self.filters.page_size = 501
		with self.assertRaisesRegex(ValueError, "500"):
			self.scope.detail_items(self.filters)

	def test_rule_counts_are_not_lost_when_revision_counts_are_added(self):
		with (
			patch.object(self.module, "context", return_value=(self.filters, Row())),
			patch.object(self.module, "rule_counts", return_value=Counter(supplier_rules=8, group_rules=3)),
			patch.object(
				self.module, "revision_stats", return_value=(Counter(draft_revisions=2), Counter(), {})
			),
			patch.object(self.module, "location_rows", return_value=[]),
			patch.object(self.module, "coverage", return_value=Counter({"Standard price": 5000})),
		):
			_columns, rows, _message, _chart = self.module.overview(self.filters)
		self.assertEqual(rows[0]["supplier_rules"], 8)
		self.assertEqual(rows[0]["group_rules"], 3)
		self.assertEqual(rows[0]["active_items"], 5000)

	def test_saved_scope_is_private_and_explicit_widget_scope_wins(self):
		saved = {"company": "Company A", "price_list": "Retail", "item_group": "GROUP"}
		self.frappe.defaults.get_user_default.side_effect = lambda key: (
			self.frappe.as_json(saved) if key == self.module.SCOPE_KEY else "Company A"
		)
		self.frappe.get_list.side_effect = lambda dt, **kwargs: (
			[Row(company="Company A", price_list="Retail")]
			if dt == "Selling Price List Policy"
			else self.data(2)
		)
		filters, _config = self.module.context(Row())
		self.assertEqual(filters.item_group, "GROUP")
		filters, _config = self.module.context(Row(item_group="OTHER"))
		self.assertEqual(filters.item_group, "OTHER")
		self.frappe.defaults.set_user_default = Mock()
		self.module.save_dashboard_scope(
			{"company": "Company A", "price_list": "Retail", "item_group": "GROUP"}
		)
		args = self.frappe.defaults.set_user_default.call_args
		self.assertEqual(args.args[0], self.module.SCOPE_KEY)
		self.assertEqual(len(args.args), 2)  # no caller-selected other user

	def test_historical_scope_retains_disabled_items(self):
		self.filters.item_group = "GROUP"
		self.frappe.get_list.return_value = [Row(name="OLD", end_of_life="2020-01-01")]
		self.assertEqual(len(self.scope.catalog(self.filters, historical=True)), 1)
		self.assertNotIn("disabled", self.frappe.get_list.call_args.kwargs["filters"])

	def report_module(self):
		utils = ModuleType("frappe.utils")
		for key in ("getdate", "add_days", "add_months", "today"):
			setattr(utils, key, getattr(self.module, key))
		package = ModuleType("av_tools.selling_pricing_engine")
		package.repository = self.repository
		package.engine = ModuleType(PREFIX + "engine")
		package.engine.calculate_row = Mock()
		self.repository.policy_for = Mock(return_value=Row(price_list="Retail"))
		self.repository.price_snapshot = Mock()
		module = load(
			"reports",
			self.frappe,
			{
				"frappe.utils": utils,
				"av_tools.selling_pricing_engine": package,
				PREFIX + "access": self.access,
				PREFIX + "coverage": self.coverage_module,
				PREFIX + "report_scope": self.scope,
			},
		)
		return module, package.engine

	def test_missing_price_report_skips_cost_work_for_priced_items(self):
		report, engine = self.report_module()
		self.filters.item_group = "GROUP"
		items = self.data(1000)

		def read(doctype, **kwargs):
			if doctype == "Item":
				return items
			if doctype == "Item Price":
				rows = [
					Row(name=item.name, item_code=item.name, uom="Nos", currency="TZS", price_list_rate=100)
					for item in items
					if item.name in kwargs["filters"]["item_code"][1]
				]
				start = kwargs.get("limit_start", 0)
				return rows[start : start + kwargs["limit_page_length"]]
			raise AssertionError(doctype)

		self.frappe.get_list.side_effect = read
		_columns, rows, message = report.run_report("Missing Selling Prices", self.filters)
		self.assertEqual(rows, [])
		self.assertIn("1000", message)
		engine.calculate_row.assert_not_called()

	def test_history_pages_skip_snapshots_and_preserve_unknown_margin(self):
		report, _engine = self.report_module()
		self.filters.item_group = "GROUP"

		def read(doctype, **kwargs):
			if doctype == "Item" and not kwargs.get("pluck"):
				return self.data(1)
			if doctype == "Selling Price Revision":
				return [Row(name="REV", published_on="2026-11-01", published_by="manager")]
			return kwargs["filters"]["name"][1]

		self.frappe.get_list.side_effect = read
		self.frappe.get_all.return_value = [
			Row(
				parent="REV",
				item_code="SKU-00000",
				result="Published",
				cost_available=0,
				cost_rate=0,
				proposed_margin=0,
			)
		]
		_columns, rows, message = report.history(self.filters, Row())
		self.assertIsNone(rows[0]["proposed_margin"])
		self.assertIsNone(rows[0]["cost_rate"])
		self.assertIn("1 permitted records", message)
		self.frappe.get_doc.assert_not_called()
		self.assertNotIn("calculation_snapshot", self.frappe.get_all.call_args.kwargs["fields"])


if __name__ == "__main__":
	unittest.main()
