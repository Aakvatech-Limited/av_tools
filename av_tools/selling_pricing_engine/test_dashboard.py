"""Isolated dashboard tests: counts, effective coverage, permissions and asset wiring."""

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from av_tools.selling_pricing_engine.test_pricing import PREFIX, Row, access_stub, load, make_frappe

ROOT = Path(__file__).resolve().parent


class TestPricingDashboard(unittest.TestCase):
	def setUp(self):
		self.frappe = make_frappe()
		self.frappe.get_cached_doc = Mock(
			return_value=Row(name="Retail", enabled=1, selling=1, currency="TZS")
		)
		self.frappe.defaults = SimpleNamespace(get_user_default=Mock(return_value="Company A"))
		self.frappe.utils = SimpleNamespace(escape_html=lambda text: text)
		self.access = access_stub()
		self.access.manager = Mock()
		self.access.check_link = Mock()
		self.policies = load("policies", self.frappe, {PREFIX + "access": self.access})
		self.access.settings.return_value = Row(max_revision_items=500)
		self.repository = ModuleType(PREFIX + "repository")
		self.repository.uom_factor = Mock(return_value=2)

		def valid_price(rows, day):
			matches = [r for r in rows if self.module.effective(r, date.fromisoformat(str(day)[:10]))]
			if len(matches) > 1:
				raise ValueError("Overlapping prices")
			return matches[0] if matches else None

		self.repository.valid_price = Mock(side_effect=valid_price)
		# Stub the namespace too: importing repository must not initialize real Frappe.
		package = ModuleType("av_tools.selling_pricing_engine")
		package.repository = self.repository
		utils = ModuleType("frappe.utils")
		utils.getdate = lambda value=None: date.fromisoformat(str(value or "2026-11-03")[:10])
		utils.today = lambda: "2026-11-03"
		utils.add_days = lambda value, days: str(utils.getdate(value) + timedelta(days=days))

		def add_months(value, months):
			value = utils.getdate(value)
			year, month = divmod(value.year * 12 + value.month - 1 + months, 12)
			return str(date(year, month + 1, 1))

		utils.add_months = add_months
		self.scope = load(
			"report_scope", self.frappe, {PREFIX + "policies": self.policies, "frappe.utils": utils}
		)
		self.locations = ModuleType(PREFIX + "locations")
		self.locations.branch_for = Mock(return_value=None)
		self.coverage_module = load(
			"coverage",
			self.frappe,
			{
				"av_tools.selling_pricing_engine": package,
				PREFIX + "repository": self.repository,
				PREFIX + "access": self.access,
				PREFIX + "report_scope": self.scope,
				PREFIX + "locations": self.locations,
				"frappe.utils": utils,
			},
		)
		self.module = load(
			"dashboard",
			self.frappe,
			{
				"av_tools.selling_pricing_engine": package,
				"frappe.utils": utils,
				PREFIX + "repository": self.repository,
				PREFIX + "access": self.access,
				PREFIX + "policies": self.policies,
				PREFIX + "report_scope": self.scope,
				PREFIX + "coverage": self.coverage_module,
			},
		)
		self.filters = Row(company="Company A", price_list="Retail", as_on="2026-11-03")

	def row(self, **kwargs):
		return Row(item_code="ITEM-1", result="Ready", selected=1, **kwargs)

	def revision(self, status, rows, **kwargs):
		return SimpleNamespace(status=status, docstatus=1 if status == "Published" else 0, **kwargs), rows

	def test_backlog_and_publication_month_boundaries(self):
		revisions = [
			self.revision("Draft", []),
			self.revision(
				"Calculated",
				[
					Row(result="Blocked", selected=0),
					Row(result="Requires Review"),
					Row(
						result="Requires Review",
						acknowledge_unknown_margin=1,
						review_note="Reviewed by manager",
					),
				],
			),
			self.revision("Published", [], published_on="2026-11-01 10:00:00"),
			self.revision("Published", [], published_on="2026-10-31 10:00:00"),
			self.revision("Published", [], published_on="2026-11-04 10:00:00"),
		]
		counts, pipeline, trend = self.module.summarize_revisions(revisions, self.filters)
		self.assertEqual(counts["draft_revisions"], 1)
		self.assertEqual(counts["calculated_revisions"], 1)
		self.assertEqual(counts["blocked_rows"], 1)
		self.assertEqual(counts["review_rows"], 1)
		self.assertEqual(counts["published_month"], 1)
		self.assertEqual(pipeline["Published"], 3)
		self.assertEqual(list(trend), ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"])
		self.assertEqual(trend["2026-11"], 1)

	def test_access_denied_before_any_queries(self):
		self.frappe.get_roles.return_value = ["Sales User"]
		with self.assertRaises(PermissionError):
			self.module.context(self.filters)
		self.frappe.get_list.assert_not_called()

	def test_ambiguous_policy_never_selects_first(self):
		self.frappe.get_list.return_value = [
			Row(company="Company A", price_list="Retail"),
			Row(company="Company A", price_list="Wholesale"),
		]
		with self.assertRaisesRegex(ValueError, "Select a Company"):
			self.module.context(Row())

	def test_context_enforces_links_and_enabled_settings(self):
		self.frappe.get_list.return_value = [Row(company="Company A", price_list="Retail")]
		self.module.context(self.filters)
		self.access.check_context.assert_called_once_with("Company A", "Retail", None, None)
		self.access.settings.assert_called_once_with("Company A")

	def test_row_limit_errors_instead_of_truncating(self):
		self.frappe.get_list.return_value = [Row()] * (self.module.MAX_ROWS + 1)
		with self.assertRaisesRegex(ValueError, "5,000"):
			self.module.bounded("Item Price")

	def test_revision_rows_obey_link_permissions_and_mixed_warehouse_filters(self):
		self.filters.warehouse = "WH-A"

		def get_list(doctype, **kwargs):
			if doctype == "Selling Price Revision":
				return [Row(name="REV-1", docstatus=0, status="Calculated")]
			return [name for name in kwargs["filters"]["name"][1] if name != "HIDDEN"]

		self.frappe.get_list.side_effect = get_list
		self.frappe.get_all.side_effect = lambda dt, **kwargs: (
			["REV-1"]
			if kwargs.get("pluck")
			else [
				Row(parent="REV-1", item_code="VISIBLE", warehouse="WH-A", result="Blocked"),
				Row(parent="REV-1", item_code="HIDDEN", warehouse="WH-A", result="Blocked"),
			]
		)
		counts, _pipeline, _trend = self.module.revision_stats(self.filters)
		self.assertEqual(counts["blocked_rows"], 1)
		self.frappe.get_doc.assert_not_called()
		read = self.frappe.get_all.call_args.kwargs
		self.assertEqual(read["filters"]["warehouse"], "WH-A")
		self.assertEqual(read["filters"]["parent"], ["in", ["REV-1"]])
		self.assertNotIn("calculation_snapshot", read["fields"])

	def price(self, name="PRICE-1", **kwargs):
		return Row(name=name, item_code="ITEM-1", uom="Nos", currency="TZS", price_list_rate=100, **kwargs)

	def coverage(self, prices, locations=None, sales_uom="Nos"):
		def read(doctype, **kwargs):
			if doctype == "Item":
				return [Row(name="ITEM-1", stock_uom="Nos", sales_uom=sales_uom)]
			if doctype == "Item Price":
				return prices
			if doctype == "Location Selling Price":
				return [row for row in locations or [] if row.warehouse == kwargs["filters"].get("warehouse")]
			raise AssertionError(doctype)

		self.frappe.get_list.side_effect = read
		return self.module.coverage(self.filters, Row(max_revision_items=500), locations or [])

	def test_effective_prices_exclude_customer_specific_and_future_prices(self):
		counts = self.coverage(
			[self.price(customer="CUSTOMER"), self.price("FUTURE", valid_from="2026-11-04")]
		)
		self.assertEqual(counts["Missing"], 1)

	def test_location_precedence_and_no_other_warehouse_borrowing(self):
		self.filters.warehouse = "WH-A"
		local = Row(name="LOCAL", item_code="ITEM-1", warehouse="WH-A", uom="Nos", currency="TZS", rate=100)
		self.assertEqual(self.coverage([self.price()], [local])["Location override"], 1)
		local.warehouse = "WH-B"
		self.assertEqual(self.coverage([], [local])["Missing"], 1)

	def test_overlap_is_a_separate_exception_not_covered_or_missing(self):
		counts = self.coverage([self.price(), self.price("PRICE-2")])
		self.assertEqual(counts["Invalid / overlapping"], 1)
		self.assertEqual(counts["Missing"], 0)

	def test_stock_uom_fallback_requires_valid_conversion(self):
		self.frappe.get_all.return_value = [Row(parent="ITEM-1", uom="Box", conversion_factor=2)]
		self.assertEqual(self.coverage([self.price()], sales_uom="Box")["Standard price"], 1)
		self.frappe.get_all.return_value = []
		self.assertEqual(self.coverage([self.price()], sales_uom="Box")["Invalid / overlapping"], 1)

	def test_unknown_currency_is_not_coverage(self):
		price = self.price()
		price.currency = "USD"
		self.assertEqual(self.coverage([price])["Invalid / overlapping"], 1)

	def test_expiring_prices_includes_today_and_day_30_only(self):
		with (
			patch.object(self.module, "context", return_value=(self.filters, Row())),
			patch.object(
				self.module,
				"location_rows",
				return_value=[
					Row(valid_upto="2026-11-03"),
					Row(valid_upto="2026-12-03"),
					Row(valid_upto="2026-12-04"),
					Row(),
				],
			),
		):
			self.filters.metric = "expiring_locations"
			_columns, rows, _message, _chart = self.module.overview(self.filters)
		self.assertEqual(rows[0]["expiring_locations"], 2)
		self.assertNotIn("missing_prices", rows[0])

	def test_dashboard_assets_and_workspace_links_resolve(self):
		assets = [json.loads(path.read_text()) for path in ROOT.glob("*/*/*.json")]
		by_type = {}
		for doc in assets:
			by_type.setdefault(doc["doctype"], {})[doc["name"]] = doc
		dashboard = by_type["Dashboard"]["Sales Manager Pricing"]
		self.assertEqual(len(dashboard["cards"]), 16)
		self.assertEqual(len(dashboard["charts"]), 6)
		for card in dashboard["cards"]:
			doc = by_type["Number Card"][card["card"]]
			self.assertIn(doc["report_field"], self.module.METRICS)
			self.assertEqual(doc["report_field"], json.loads(doc["filters_json"])["metric"])
			self.assertIn(doc["report_name"], by_type["Report"])
		for chart in dashboard["charts"]:
			doc = by_type["Dashboard Chart"][chart["chart"]]
			self.assertIn(json.loads(doc["filters_json"])["chart_view"], self.module.VIEWS)
			self.assertEqual({role["role"] for role in doc["roles"]}, {"Sales Manager", "System Manager"})

	def test_unknown_margin_is_not_counted_as_zero_margin(self):
		doc = SimpleNamespace(docstatus=0, status="Calculated")
		rows = [
			Row(result="Requires Review", cost_available=0, proposed_margin=0, minimum_margin=15),
			Row(
				result="Blocked",
				cost_available=1,
				proposed_margin=10,
				minimum_margin=15,
				price_source="Base Price Fallback",
				cost_source="Invoice",
			),
		]
		counts, _pipeline, _trend = self.module.summarize_revisions([(doc, rows)], self.filters)
		self.assertEqual(counts["below_margin"], 1)
		self.assertEqual(counts["fallback_rows"], 1)
		self.assertEqual(counts["source:No usable cost"], 1)
		self.assertEqual(counts["source:Invoice"], 1)

	def test_expanded_rule_counts_observe_dates_and_link_permissions(self):
		rules = [
			Row(name="Supplier", supplier="SUP"),
			Row(name="Group", item_group="GROUP"),
			Row(name="Hidden", supplier="HIDDEN"),
			Row(name="Future", item_group="GROUP", valid_from="2026-12-01"),
		]
		self.frappe.get_list.side_effect = lambda dt, **kwargs: (
			rules
			if dt == "Selling Price Rule"
			else [name for name in kwargs["filters"]["name"][1] if name != "HIDDEN"]
		)
		counts = self.module.rule_counts(self.filters, Row(enable_phase_2=1))
		self.assertEqual(counts["supplier_rules"], 1)
		self.assertEqual(counts["group_rules"], 1)
		self.assertEqual(self.module.rule_counts(self.filters, Row(enable_phase_2=0)), {})


class TestDashboardSync(unittest.TestCase):
	def test_install_and_repeat_migrate_preserve_existing_assets(self):
		import importlib.util
		import sys

		state = {("Number Card", "Missing Selling Prices"): Row(label="My existing label")}
		f = ModuleType("frappe")
		f.throw = lambda message: (_ for _ in ()).throw(ValueError(message))
		f.get_app_path = lambda app, module: str(ROOT.parent / module)
		f.db = SimpleNamespace(exists=lambda doctype, name: (doctype, name) in state)
		f.get_doc = lambda doctype, name: state[(doctype, name)]
		imports = ModuleType("frappe.modules.import_file")

		def import_file(path, **kwargs):
			doc = json.loads(Path(path).read_text())
			if doc["doctype"] == "Dashboard":
				doc = SimpleNamespace(
					cards=[Row(x) for x in doc["cards"]], charts=[Row(x) for x in doc["charts"]]
				)
				name = json.loads(Path(path).read_text())["name"]
			else:
				name = doc["name"]
			state[(json.loads(Path(path).read_text())["doctype"], name)] = doc

		imports.import_file_by_path = Mock(side_effect=import_file)
		spec = importlib.util.spec_from_file_location(
			"isolated_dashboard_sync", ROOT.parent / "dashboard_sync.py"
		)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"frappe": f, "frappe.modules.import_file": imports}):
			spec.loader.exec_module(module)
		module.execute()
		self.assertIn(("Dashboard", "Sales Manager Pricing"), state)
		self.assertEqual(state[("Number Card", "Missing Selling Prices")].label, "My existing label")
		calls = imports.import_file_by_path.call_count
		module.execute()
		self.assertEqual(imports.import_file_by_path.call_count, calls)


if __name__ == "__main__":
	unittest.main()
