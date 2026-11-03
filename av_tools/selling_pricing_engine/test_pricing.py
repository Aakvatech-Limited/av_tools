"""Isolated behavior tests: python -m unittest av_tools.selling_pricing_engine.test_pricing -v.

Frappe doubles are scoped to imports of the module under test; no live site's
global frappe module is replaced. Persistence tests live in test_integration.py.
"""

import copy
import hashlib
import importlib.util
import json
import sys
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from av_tools.selling_pricing_engine.calculation import calculate, choose_rule, margin, number
from av_tools.selling_pricing_engine.import_prices import parse_prices

ROOT = Path(__file__).resolve().parent
PREFIX = "av_tools.selling_pricing_engine."


class Row(dict):
	def __getattr__(self, name):
		return self.get(name)

	def __setattr__(self, name, value):
		self[name] = value

	def as_dict(self):
		return dict(self)


def throw(message, exc=ValueError):
	raise exc(message)


def make_frappe():
	f = ModuleType("frappe")
	f._dict, f._, f.throw = Row, lambda x: x, throw
	f.ValidationError, f.PermissionError = ValueError, PermissionError
	f.whitelist = lambda **kwargs: lambda fn: fn
	f.session = Row(user="pricing@example.com")
	f.as_json = lambda obj: json.dumps(obj, sort_keys=True, default=str)
	f.parse_json = lambda value: json.loads(value) if isinstance(value, str) else value
	f.db = SimpleNamespace(exists=Mock(return_value=True))
	f.get_cached_value = Mock(return_value="TZS")
	f.get_doc, f.new_doc, f.has_permission = Mock(), Mock(), Mock(return_value=True)
	f.get_all, f.get_list, f.get_roles = (
		Mock(return_value=[]),
		Mock(return_value=[]),
		Mock(return_value=["Sales Manager"]),
	)
	return f


def access_stub():
	a = ModuleType(PREFIX + "access")
	a.SETTINGS, a.POLICY, a.RULE = "Selling Price Settings", "Selling Price List Policy", "Selling Price Rule"
	a.REVISION, a.LOCATION = "Selling Price Revision", "Location Selling Price"
	a.check_context, a.check_native_price_writes, a.settings = Mock(), Mock(), Mock()
	return a


def load(name, frappe, dependencies=None):
	utils = ModuleType("frappe.utils")
	utils.getdate = lambda value=None: date.fromisoformat(str(value or "2026-11-03")[:10])
	utils.get_datetime = lambda value: datetime.fromisoformat(str(value))
	utils.today = lambda: "2026-11-03"
	utils.now_datetime = lambda: datetime(2026, 11, 3, 10)
	utils.flt = lambda value: float(value or 0)
	utils.cint = lambda value: int(value or 0) if str(value or 0).isdigit() else 0
	utils.add_days = lambda value, days: (
		utils.getdate(value) + __import__("datetime").timedelta(days=days)
	).isoformat()
	document = ModuleType("frappe.model.document")
	document.Document = type("Document", (), {})
	modules = {
		"frappe": frappe,
		"frappe.utils": utils,
		"frappe.model.document": document,
		**(dependencies or {}),
	}
	spec = importlib.util.spec_from_file_location("isolated_spe_" + name, ROOT / (name + ".py"))
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, modules):
		spec.loader.exec_module(module)
	return module


class TestCalculation(unittest.TestCase):
	def test_markup_and_margin_are_different(self):
		self.assertEqual(calculate(1000, "Markup Percentage", 20)[1], 1200)
		self.assertEqual(calculate(1000, "Target Gross Margin", 20)[1], 1250)
		self.assertEqual(margin(1000, 1250), 20)

	def test_fixed_addition_and_fixed_price(self):
		self.assertEqual(calculate(1000, "Fixed Addition", 200)[1], 1200)
		self.assertEqual(calculate(None, "Fixed Selling Price", 1725)[1], 1725)

	def test_explicit_zero_is_not_missing(self):
		self.assertEqual(calculate(1000, "Markup Percentage", 0)[1], 1000)
		with self.assertRaises(ValueError):
			calculate(1000, "Markup Percentage", None)

	def test_rounding_ties_up_and_direction(self):
		self.assertEqual(calculate(None, "Fixed Selling Price", 1025, "Nearest", 50)[1], 1050)
		self.assertEqual(calculate(None, "Fixed Selling Price", 1026, "Round Down", 50)[1], 1000)
		self.assertEqual(calculate(None, "Fixed Selling Price", 1001, "Round Up", 50)[1], 1050)

	def test_rounding_can_reduce_margin_below_minimum(self):
		_rate, rounded = calculate(1000, "Target Gross Margin", 20, "Round Down", 100)
		self.assertEqual(rounded, 1200)
		self.assertLess(margin(1000, rounded), 20)

	def test_nonfinite_and_invalid_values_fail(self):
		for value in ("NaN", "Infinity", "-Infinity", None, "invalid"):
			with self.subTest(value=value), self.assertRaises(ValueError):
				number(value)
		for method, value in (
			("Target Gross Margin", 100),
			("Markup Percentage", -1),
			("Fixed Selling Price", 0),
		):
			with self.subTest(method=method), self.assertRaises(ValueError):
				calculate(1000, method, value)

	def test_no_implicit_zero_cost(self):
		for cost in (None, 0, -1):
			with self.subTest(cost=cost), self.assertRaises(ValueError):
				calculate(cost, "Markup Percentage", 20)
		self.assertIsNone(margin(None, 1000))

	def test_storage_precision_and_positive_result(self):
		self.assertEqual(calculate(1000, "Target Gross Margin", 30)[1], Decimal("1428.571429"))
		with self.assertRaises(ValueError):
			calculate(None, "Fixed Selling Price", 1, "Round Down", 100)

	def test_precedence_and_exact_uom(self):
		rules = [
			Row(name="Global list"),
			Row(name="Warehouse", warehouse="HQ"),
			Row(name="Item", item_code="I"),
			Row(name="Item warehouse", item_code="I", warehouse="HQ"),
		]
		self.assertEqual(choose_rule(rules, "I", "HQ", "Nos", "2026-11-03").name, "Item warehouse")
		rules.append(Row(name="Specific UOM", item_code="I", warehouse="HQ", uom="Nos"))
		self.assertEqual(choose_rule(rules, "I", "HQ", "Nos", "2026-11-03").name, "Specific UOM")

	def test_disabled_future_and_conflicting_rules(self):
		rules = [
			Row(name="Disabled", disabled=1),
			Row(name="Future", valid_from="2027-01-01"),
			Row(name="Expired", valid_upto="2026-11-02"),
		]
		self.assertIsNone(choose_rule(rules, "I", "HQ", "Nos", "2026-11-03"))
		with self.assertRaisesRegex(ValueError, "conflict"):
			choose_rule([Row(name="A"), Row(name="B")], "I", "HQ", "Nos", "2026-11-03")


class TestImport(unittest.TestCase):
	HEADER = "item_code,warehouse,rate,uom,currency,tax_basis\n"

	def parse(self, body, **kwargs):
		return parse_prices(self.HEADER + body, currency="TZS", **kwargs)

	def test_mapped_fixed_and_blank_fallback(self):
		rows = self.parse("I,HQ,1725,Nos,TZS,Tax Exclusive\nI,Other,,Nos,TZS,Tax Exclusive")
		self.assertEqual(rows[0]["fixed_rate"], 1725)
		self.assertIsNone(rows[1]["fixed_rate"])

	def test_blank_location_means_standard_price(self):
		self.assertIsNone(self.parse("I,,1700,Nos,TZS,Tax Exclusive")[0]["warehouse"])

	def test_zero_nonfinite_and_wrong_tax_currency_rejected(self):
		for body in (
			"I,HQ,0,Nos,TZS,Tax Exclusive",
			"I,HQ,NaN,Nos,TZS,Tax Exclusive",
			"I,HQ,100,Nos,USD,Tax Exclusive",
			"I,HQ,100,Nos,TZS,Tax Inclusive",
		):
			with self.subTest(body=body), self.assertRaises(ValueError):
				self.parse(body)

	def test_duplicates_missing_columns_and_size_limit(self):
		with self.assertRaisesRegex(ValueError, "duplicate"):
			self.parse("I,HQ,100,Nos,TZS,Tax Exclusive\nI,HQ,110,Nos,TZS,Tax Exclusive")
		with self.assertRaises(ValueError):
			parse_prices("item_code,rate\nI,100", currency="TZS")
		with self.assertRaisesRegex(ValueError, "limit"):
			self.parse("I,HQ,100,Nos,TZS,Tax Exclusive\nJ,HQ,100,Nos,TZS,Tax Exclusive", max_items=1)

	def test_precision_is_explicit(self):
		with self.assertRaisesRegex(ValueError, "precision"):
			self.parse("I,HQ,100.1234567,Nos,TZS,Tax Exclusive")


class EngineFixture(unittest.TestCase):
	def setUp(self):
		self.frappe, self.access = make_frappe(), access_stub()
		self.store = ModuleType(PREFIX + "repository")
		self.store.item_for = Mock(return_value=Row(name="I", stock_uom="Nos", sales_uom="Nos"))
		self.store.uom_factor = Mock(return_value=Decimal(1))
		self.store.rules_for = Mock(return_value=[])
		self.store.purchase_cost = Mock(
			return_value={"cost_rate": 1200, "cost_source": "Invoice", "supplier": "S"}
		)
		self.prices = {}
		self.store.price_rows = lambda company, price_list, item, uom, warehouse=None, **kw: self.prices.get(
			(price_list, warehouse), []
		)
		self.store.valid_price = lambda rows, day: next(
			(
				p
				for p in rows
				if (not p.valid_from or str(p.valid_from) <= day)
				and (not p.valid_upto or str(p.valid_upto) >= day)
			),
			None,
		)
		self.store.price_snapshot = lambda row: dict(row) if row else None
		self.store.standard_price = lambda company, price_list, item, uom, day, **kw: self.store.valid_price(
			self.store.price_rows(company, price_list, item.name, uom), day
		)
		self.store.overlaps = lambda row, start, end: str(row.valid_from or "1900-01-01") <= str(
			end or "9999-12-31"
		) and str(row.valid_upto or "9999-12-31") >= str(start)
		self.store.digest = lambda value: hashlib.sha256(
			json.dumps(value, default=str, sort_keys=True).encode()
		).hexdigest()
		self.engine = load(
			"engine", self.frappe, {PREFIX + "repository": self.store, PREFIX + "access": self.access}
		)
		self.config = Row(
			company="C",
			calculation_method="Markup Percentage",
			calculation_value=20,
			rounding_method="No Rounding",
			rounding_increment=1,
			minimum_margin=15,
			rate_precision=6,
			retain_price_decreases=1,
		)
		self.policy = Row(
			price_list="Retail",
			calculation_mode="Use Default",
			rounding_mode="Use Default",
			fallback_price_list=None,
		)
		self.context = {
			"item_code": "I",
			"warehouse": "HQ",
			"uom": "Nos",
			"valid_from": "2026-11-03",
			"valid_upto": None,
		}

	def calculate(self, **kwargs):
		return self.engine.calculate_row(self.config, self.policy, self.context, **kwargs)


class TestEngine(EngineFixture):
	def test_calculation_keeps_cost_supplier_and_rule_provenance(self):
		row = self.calculate()
		self.assertEqual(row["proposed_rate"], 1440)
		self.assertEqual(row["result"], "Ready")
		self.assertEqual(row["supplier"], "S")
		self.assertTrue(row["calculation_hash"])

	def test_zero_override_does_not_inherit_default(self):
		self.policy.update(
			calculation_mode="Override", calculation_method="Markup Percentage", calculation_value=0
		)
		self.config.minimum_margin = 0
		self.assertEqual(self.calculate()["proposed_rate"], 1200)

	def test_fixed_prices_survive_cost_decrease_and_global_rounding(self):
		self.store.rules_for.return_value = [
			Row(
				name="Fixed",
				item_code="I",
				warehouse="HQ",
				uom="Nos",
				calculation_mode="Override",
				calculation_method="Fixed Selling Price",
				calculation_value=1725,
			)
		]
		self.config.update(rounding_method="Round Up", rounding_increment=1000)
		self.assertEqual(self.calculate()["proposed_rate"], 1725)
		self.store.purchase_cost.return_value["cost_rate"] = 700
		self.assertEqual(self.calculate()["proposed_rate"], 1725)

	def test_fallback_price_has_unknown_margin_not_fake_zero(self):
		self.store.purchase_cost.return_value = {"cost_rate": None, "cost_reason": "No cost"}
		self.policy.fallback_price_list = "Base"
		self.prices[("Base", None)] = [Row(name="BASE-I", price_list_rate=1700)]
		row = self.calculate()
		self.assertEqual(row["price_source"], "Base Price Fallback")
		self.assertEqual(row["result"], "Requires Review")
		self.assertIsNone(row["proposed_margin"])
		self.assertEqual(row["cost_available"], 0)

	def test_no_cost_or_fallback_is_blocked(self):
		self.store.purchase_cost.return_value = {"cost_rate": None}
		with self.assertRaisesRegex(ValueError, "No usable"):
			self.calculate()

	def test_cost_permission_errors_are_not_hidden(self):
		self.store.purchase_cost.side_effect = PermissionError("Private cost")
		with self.assertRaises(PermissionError):
			self.calculate(fixed_input=1700)

	def test_fixed_import_below_margin_is_blocked(self):
		self.store.purchase_cost.return_value["cost_rate"] = 1500
		row = self.calculate(fixed_input=1600)
		self.assertEqual(row["result"], "Blocked")
		self.assertAlmostEqual(row["proposed_margin"], 6.25)

	def test_minimum_margin_checked_after_rounding(self):
		self.config.update(
			calculation_method="Target Gross Margin",
			calculation_value=20,
			minimum_margin=20,
			rounding_method="Round Down",
			rounding_increment=100,
		)
		self.store.purchase_cost.return_value["cost_rate"] = 1000
		self.assertEqual(self.calculate()["result"], "Blocked")

	def test_supplier_savings_can_retain_the_current_price(self):
		self.prices[("Retail", "HQ")] = [Row(name="LSP", rate=2000, currency="TZS")]
		row = self.calculate()
		self.assertEqual(row["proposed_rate"], 2000)
		self.assertEqual(row["price_source"], "Retained Current Price")

	def test_stale_cost_rule_and_price_snapshots_change_hash(self):
		first = self.calculate()["calculation_hash"]
		self.store.purchase_cost.return_value["cost_rate"] = 1250
		self.assertNotEqual(first, self.calculate()["calculation_hash"])
		first = self.calculate()["calculation_hash"]
		self.prices[("Retail", "HQ")] = [Row(name="Changed", rate=2100, currency="TZS")]
		self.assertNotEqual(first, self.calculate()["calculation_hash"])
		first = self.calculate()["calculation_hash"]
		self.store.rules_for.return_value = [Row(name="New", modified="New policy")]
		self.assertNotEqual(first, self.calculate()["calculation_hash"])

	def test_future_price_overlap_blocks_preview(self):
		self.prices[("Retail", "HQ")] = [Row(name="Future", rate=1700, valid_from="2026-12-01")]
		self.assertEqual(self.calculate()["result"], "Blocked")


class TestSales(EngineFixture):
	def setUp(self):
		super().setUp()
		self.access.settings.return_value = self.config
		self.frappe.get_cached_doc = Mock(return_value=Row(name="I", is_sales_item=1, stock_uom="Nos"))
		self.frappe.get_cached_value.side_effect = lambda *args: "TZS"
		self.sales = load(
			"sales", self.frappe, {PREFIX + "repository": self.store, PREFIX + "access": self.access}
		)
		self.erp = ModuleType("erpnext.stock.get_item_details")
		self.erp.get_rate_locked_source_row = Mock(return_value=None)
		self.erp.get_price_list_rate_for = Mock(return_value=1700)
		self.store.standard_price = Mock(return_value=Row(price_list_rate=1700))
		self.ctx = Row(
			doctype="Sales Order",
			company="C",
			price_list="Retail",
			item_code="I",
			warehouse="HQ",
			uom="Nos",
			currency="TZS",
			transaction_date="2026-11-03",
			conversion_rate=1,
			plc_conversion_rate=1,
		)
		self.prices[("Retail", "HQ")] = [Row(name="LSP", rate=1725, currency="TZS")]

	def resolve(self, native=None, doc=None):
		with patch.dict(sys.modules, {"erpnext.stock.get_item_details": self.erp}):
			return self.sales.resolve_response(self.ctx, native or Row(price_list_rate=1700), doc)

	def test_location_and_standard_fallback(self):
		self.assertEqual(self.resolve()["rate"], 1725)
		self.prices.clear()
		self.assertEqual(self.resolve()["rate"], 1700)

	def test_disabled_companies_unchanged(self):
		self.access.settings.return_value = None
		original = Row(price_list_rate=1700, rate=1690)
		self.assertEqual(self.resolve(original), original)

	def test_sales_doctypes_and_returns_pos_are_excluded(self):
		for kind, key in (
			("Purchase Invoice", None),
			("Delivery Note", None),
			("Sales Invoice", "is_pos"),
			("Sales Invoice", "is_return"),
		):
			with self.subTest(kind=kind, key=key):
				self.ctx.doctype = kind
				if key:
					self.ctx[key] = 1
				self.assertEqual(self.resolve(Row(price_list_rate=100))["price_list_rate"], 100)
				if key:
					self.ctx.pop(key)

	def test_customer_pricing_rule_and_source_rates_preserved(self):
		self.assertEqual(
			self.resolve(Row(price_list_rate=1500, rate=1500, pricing_rules='["Customer Rule"]'))["rate"],
			1500,
		)
		self.erp.get_rate_locked_source_row.return_value = Row(rate=1600)
		self.assertEqual(self.resolve(Row(price_list_rate=1600, rate=1600))["rate"], 1600)
		self.erp.get_rate_locked_source_row.return_value = None
		self.ctx.customer = "Customer"
		self.frappe.get_all.return_value = [Row(uom="Nos")]
		self.assertEqual(self.resolve(Row(price_list_rate=1550, rate=1550))["rate"], 1550)

	def test_manual_rate_requires_role(self):
		self.config.manual_rate_role = "Pricing Override"
		with self.assertRaises(PermissionError):
			self.resolve(doc=Row(custom_spe_keep_manual_rates=1))
		self.frappe.get_roles.return_value = ["Pricing Override"]
		self.assertEqual(self.resolve(Row(rate=1650), Row(custom_spe_keep_manual_rates=1))["rate"], 1650)

	def test_discount_and_currency_conversion(self):
		self.ctx.update(discount_percentage=10, conversion_rate=2, plc_conversion_rate=3)
		row = self.resolve()
		self.assertEqual(row["price_list_rate"], 2587.5)
		self.assertEqual(row["rate"], 2328.75)
		self.assertNotIn("cost_rate", row)

	def test_missing_price_and_foreign_warehouse_denied(self):
		self.access.check_context.side_effect = PermissionError("Warehouse denied")
		with self.assertRaises(PermissionError):
			self.resolve()
		self.access.check_context.side_effect = None
		self.prices.clear()
		self.store.standard_price.return_value = None
		with self.assertRaisesRegex(ValueError, "No valid published"):
			self.resolve()


class TestRevisionGuards(EngineFixture):
	def setUp(self):
		super().setUp()
		self.publication = ModuleType(PREFIX + "publication")
		self.publication.publish_row = Mock()
		self.validation = ModuleType(PREFIX + "validation")
		self.validation.dates = Mock()
		self.module = load(
			"revision",
			self.frappe,
			{
				PREFIX + "engine": self.engine,
				PREFIX + "repository": self.store,
				PREFIX + "access": self.access,
				PREFIX + "publication": self.publication,
				PREFIX + "validation": self.validation,
			},
		)
		self.access.settings.return_value = self.config
		self.store.policy_for = Mock(return_value=self.policy)

	def draft(self, result=None):
		result = Row(result or self.calculate())
		result.idx = 1
		return SimpleNamespace(
			status="Calculated", company="C", price_list="Retail", name="REV", items=[result]
		)

	def test_submit_rejects_changed_preview_before_writing(self):
		doc = self.draft()
		self.store.purchase_cost.return_value["cost_rate"] = 1300
		with self.assertRaisesRegex(ValueError, "changed"):
			self.module.SellingPriceRevision.before_submit(doc)
		self.publication.publish_row.assert_not_called()

	def test_known_below_margin_never_publishes(self):
		self.store.purchase_cost.return_value["cost_rate"] = 1500
		doc = self.draft(self.calculate(fixed_input=1600))
		with self.assertRaisesRegex(ValueError, "blocked"):
			self.module.SellingPriceRevision.before_submit(doc)
		self.publication.publish_row.assert_not_called()

	def test_missing_cost_requires_explicit_acknowledgement(self):
		self.store.purchase_cost.return_value = {"cost_rate": None}
		doc = self.draft(self.calculate(fixed_input=1700))
		with self.assertRaisesRegex(ValueError, "acknowledge"):
			self.module.SellingPriceRevision.before_submit(doc)
		doc.items[0].update(
			acknowledge_unknown_margin=1, review_note="Reviewed against approved supplier schedule"
		)
		self.module.SellingPriceRevision.before_submit(doc)
		self.publication.publish_row.assert_called_once()
		self.assertEqual(doc.status, "Published")

	def test_deselected_rows_and_empty_selection_do_not_publish(self):
		doc = self.draft()
		doc.items[0].selected = 0
		with self.assertRaisesRegex(ValueError, "Select at least"):
			self.module.SellingPriceRevision.before_submit(doc)
		self.publication.publish_row.assert_not_called()

	def test_published_history_cannot_be_cancelled(self):
		with self.assertRaisesRegex(ValueError, "cannot be cancelled"):
			self.module.SellingPriceRevision.before_cancel(SimpleNamespace())

	def test_no_float_or_datetime_false_positive(self):
		self.assertEqual(self.module.comparable(None, "Currency"), self.module.comparable(0, "Currency"))
		self.assertEqual(
			self.module.comparable(date(2026, 11, 3), "Date"), self.module.comparable("2026-11-03", "Date")
		)


class TestRepository(unittest.TestCase):
	def setUp(self):
		self.frappe, self.access = make_frappe(), access_stub()
		functions = ModuleType("frappe.query_builder.functions")
		functions.IfNull = Mock()
		self.module = load(
			"repository",
			self.frappe,
			{PREFIX + "access": self.access, "frappe.query_builder.functions": functions},
		)

	def test_uom_and_currency_normalized_from_submitted_invoice(self):
		self.frappe.get_list.return_value = [Row(name="PI-1")]
		invoice = SimpleNamespace(
			name="PI-1",
			company="C",
			docstatus=1,
			is_return=0,
			supplier="Supplier",
			posting_date="2026-11-01",
			modified="2026-11-02 10:00:00",
			items=[Row(name="ROW-1", idx=1, item_code="I", stock_qty=2, base_net_amount=2400)],
			check_permission=Mock(),
		)
		self.frappe.get_doc.return_value = invoice
		item = Row(name="I", stock_uom="Nos", uoms=[Row(uom="Box", conversion_factor=10)])
		with patch.object(self.module, "exchange_rate", return_value=(Decimal("0.001"), "FX-1")):
			cost = self.module.purchase_cost("C", item, "Box", "USD", "2026-11-03", lock=True)
		self.assertEqual(cost["cost_rate"], 12)
		self.assertEqual(cost["source_invoice_item"], "ROW-1")
		self.assertEqual(cost["exchange_reference"], "FX-1")
		self.frappe.get_doc.assert_called_with("Purchase Invoice", "PI-1", for_update=True)
		filters = self.frappe.get_list.call_args.kwargs["filters"]
		self.assertIn(["Purchase Invoice", "company", "=", "C"], filters)
		self.assertIn(["Purchase Invoice", "docstatus", "=", 1], filters)
		self.assertIn(["Purchase Invoice", "is_return", "=", 0], filters)

	def test_unknown_uom_is_not_assumed_one(self):
		with self.assertRaises(ValueError):
			self.module.uom_factor(Row(stock_uom="Nos", uoms=[]), "Box")

	def test_standard_fallback_uses_stock_uom_conversion(self):
		item = Row(name="I", stock_uom="Nos", uoms=[Row(uom="Box", conversion_factor=10)])
		stock_price = Row(name="IP", uom="Nos", currency="TZS", price_list_rate=1700)
		self.module.price_rows = Mock(
			side_effect=lambda company, pl, code, uom, **kw: [stock_price] if uom == "Nos" else []
		)
		self.frappe.get_cached_value.side_effect = (
			lambda dt, name, field: 0 if field == "price_not_uom_dependent" else "TZS"
		)
		price = self.module.standard_price("C", "Retail", item, "Box", "2026-11-03")
		self.assertEqual(price.price_list_rate, 17000)
		self.assertEqual(price.normalization_factor, 10)
		self.assertEqual(price.source_uom, "Nos")

	def test_price_not_uom_dependent_retains_the_rate(self):
		item = Row(name="I", stock_uom="Nos", uoms=[Row(uom="Box", conversion_factor=10)])
		self.module.price_rows = Mock(
			side_effect=lambda company, pl, code, uom, **kw: [
				Row(name="IP", uom="Nos", currency="TZS", price_list_rate=1700)
			]
			if uom == "Nos"
			else []
		)
		self.frappe.get_cached_value.side_effect = (
			lambda dt, name, field: 1 if field == "price_not_uom_dependent" else "TZS"
		)
		self.assertEqual(
			self.module.standard_price("C", "Retail", item, "Box", "2026-11-03").price_list_rate, 1700
		)

	def test_mismatched_currency_is_never_used_as_a_fallback(self):
		self.module.price_rows = Mock(
			return_value=[Row(name="IP", uom="Nos", currency="USD", price_list_rate=1700)]
		)
		with self.assertRaisesRegex(ValueError, "currency"):
			self.module.standard_price("C", "Retail", Row(name="I", stock_uom="Nos"), "Nos", "2026-11-03")

	def test_overlapping_published_prices_are_an_error(self):
		with self.assertRaisesRegex(ValueError, "Overlapping"):
			self.module.valid_price([Row(name="A"), Row(name="B")], "2026-11-03")

	def test_dates_are_inclusive_and_zero_is_not_missing(self):
		self.assertEqual(
			self.module.valid_price(
				[Row(name="A", valid_from="2026-11-03", valid_upto="2026-11-03", rate=0)], "2026-11-03"
			).name,
			"A",
		)
		self.assertIsNone(self.module.valid_price([Row(valid_from="2026-11-04")], "2026-11-03"))


class TestPublication(unittest.TestCase):
	def setUp(self):
		self.frappe, self.access = make_frappe(), access_stub()
		store = ModuleType(PREFIX + "repository")
		store.price_rows = Mock(return_value=[])
		store.overlaps = lambda row, start, end: str(row.valid_from or "1900-01-01") <= str(
			end or "9999-12-31"
		) and str(row.valid_upto or "9999-12-31") >= str(start)
		self.module = load(
			"publication", self.frappe, {PREFIX + "repository": store, PREFIX + "access": self.access}
		)
		self.doc = Row(company="C", price_list="Retail", name="REV", calculated_on="2026-11-03 10:00:00")
		self.row = Row(
			item_code="I",
			uom="Nos",
			currency="TZS",
			proposed_rate=1725,
			valid_from="2026-11-03",
			price_source="Calculated Rule",
		)
		self.price = Row(name="IP-1", flags=Row())
		self.price.save = Mock()
		self.frappe.new_doc.return_value = self.price

	def test_new_standard_price_requires_native_write_permissions(self):
		self.module.publish_row(self.doc, self.row)
		self.assertEqual(self.price.price_list_rate, 1725)
		self.assertEqual(self.price.custom_spe_revision, "REV")
		self.frappe.has_permission.assert_any_call("Item Price", "write", throw=True)
		self.frappe.has_permission.assert_any_call("Item Price", "create", throw=True)

	def test_same_start_updates_the_existing_price(self):
		self.module.store.price_rows.return_value = [Row(name="IP-1", valid_from="2026-11-03")]
		self.frappe.get_doc.return_value = self.price
		self.module.publish_row(self.doc, self.row)
		self.frappe.new_doc.assert_not_called()
		self.assertEqual(self.row.published_price, "IP-1")

	def test_previous_interval_is_closed_before_new_price(self):
		old = Row(name="OLD", flags=Row())
		old.save = Mock()
		self.module.store.price_rows.return_value = [Row(name="OLD", valid_from="2026-11-01")]
		self.frappe.get_doc.return_value = old
		self.module.publish_row(self.doc, self.row)
		self.assertEqual(old.valid_upto, "2026-11-02")
		old.save.assert_called_once()

	def test_future_overlap_causes_no_writes(self):
		self.module.store.price_rows.return_value = [Row(name="FUTURE", valid_from="2026-12-01")]
		with self.assertRaisesRegex(ValueError, "future"):
			self.module.publish_row(self.doc, self.row)
		self.price.save.assert_not_called()

	def test_location_price_is_company_scoped_and_audited(self):
		self.row.warehouse = "HQ"
		self.module.publish_row(self.doc, self.row)
		self.assertEqual(self.price.company, "C")
		self.assertEqual(self.price.warehouse, "HQ")
		self.assertEqual(self.price.rate, 1725)
		self.assertTrue(self.price.flags.spe_publishing)
		self.assertEqual(self.row.published_doctype, "Location Selling Price")


class TestShippedContract(unittest.TestCase):
	def test_six_doctypes_and_five_reports_with_valid_fields(self):
		doctypes = list((ROOT / "doctype").glob("*/*.json"))
		self.assertEqual(len(doctypes), 6)
		for path in doctypes:
			doc = json.loads(path.read_text())
			self.assertEqual(doc["module"], "Selling Pricing Engine")
			fields = [field["fieldname"] for field in doc["fields"]]
			self.assertEqual(fields, doc["field_order"])
			self.assertEqual(len(fields), len(set(fields)))
		self.assertEqual(len(list((ROOT / "report").glob("*/*.json"))), 5)

	def test_cost_fields_are_not_visible_to_sales_user(self):
		doc = json.loads((ROOT / "doctype/location_selling_price/location_selling_price.json").read_text())
		for field in doc["fields"]:
			if field["fieldname"] in ("cost_rate", "supplier", "source_invoice"):
				self.assertEqual(field["permlevel"], 1)
		self.assertFalse(
			any(p["role"] == "Sales User" and p.get("permlevel") == 1 for p in doc["permissions"])
		)

	def test_default_disabled_and_published_history_not_cancellable(self):
		doc = json.loads((ROOT / "doctype/selling_price_settings/selling_price_settings.json").read_text())
		self.assertEqual(next(f for f in doc["fields"] if f["fieldname"] == "enabled")["default"], "0")
		doc = json.loads((ROOT / "doctype/selling_price_revision/selling_price_revision.json").read_text())
		self.assertTrue(doc["is_submittable"])
		self.assertFalse(any(p.get("cancel") for p in doc["permissions"]))

	def test_navigation_targets_are_shipped(self):
		workspace = json.loads(
			(ROOT / "workspace/selling_pricing_engine/selling_pricing_engine.json").read_text()
		)
		for link in workspace["links"]:
			if link["type"] != "Link":
				continue
			kind, name = link["link_type"].lower(), link["link_to"].lower().replace(" ", "_")
			self.assertTrue((ROOT / kind / name / (name + ".json")).is_file())


if __name__ == "__main__":
	unittest.main()
