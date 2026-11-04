"""Phase 2 regression tests. No bench or customer data is needed."""

import unittest
from decimal import Decimal
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from av_tools.selling_pricing_engine.calculation import choose_rule, matching_rules
from av_tools.selling_pricing_engine.test_pricing import (
	PREFIX,
	EngineFixture,
	Row,
	access_stub,
	load,
	make_frappe,
)


class TestExpandedPrecedence(unittest.TestCase):
	def choose(self, rules, **kwargs):
		return choose_rule(
			rules,
			"ITEM",
			"WH",
			"Nos",
			"2026-11-04",
			supplier="SUP",
			branch="BR",
			item_groups=["Leaf", "Parent"],
			**kwargs,
		)

	def test_source_hierarchy_and_branch_insertions(self):
		scopes = [
			{"item_code": "ITEM", "warehouse": "WH", "supplier": "SUP"},
			{"item_code": "ITEM", "warehouse": "WH"},
			{"item_code": "ITEM", "branch": "BR", "supplier": "SUP"},
			{"item_code": "ITEM", "branch": "BR"},
			{"item_code": "ITEM", "supplier": "SUP"},
			{"item_code": "ITEM"},
			{"item_group": "Leaf", "warehouse": "WH"},
			{"item_group": "Leaf", "branch": "BR"},
			{"item_group": "Leaf"},
			{"supplier": "SUP", "warehouse": "WH"},
			{"supplier": "SUP", "branch": "BR"},
			{"supplier": "SUP"},
			{"warehouse": "WH"},
			{"branch": "BR"},
			{},
		]
		rules = [Row(name=str(i), **scope) for i, scope in enumerate(scopes)]
		for index in range(len(rules)):
			self.assertEqual(self.choose(list(reversed(rules[index:]))).name, str(index))

	def test_parent_group_requires_explicit_inheritance(self):
		rule = Row(name="parent", item_group="Parent")
		self.assertIsNone(self.choose([rule]))
		rule.include_child_groups = 1
		self.assertEqual(self.choose([rule]).name, "parent")
		self.assertEqual(self.choose([rule, Row(name="leaf", item_group="Leaf")]).name, "leaf")

	def test_ties_and_supplier_mismatch_are_not_arbitrary(self):
		with self.assertRaisesRegex(ValueError, "Equally specific"):
			self.choose([Row(name="A", supplier="SUP"), Row(name="B", supplier="SUP")])
		self.assertIsNone(self.choose([Row(name="Other", supplier="OTHER")]))

	def test_exact_uom_stays_within_scope_tier(self):
		self.assertEqual(
			self.choose(
				[Row(name="item", item_code="ITEM"), Row(name="supplier", supplier="SUP", uom="Nos")]
			).name,
			"item",
		)


class TestExpandedEngine(EngineFixture):
	def setUp(self):
		super().setUp()
		self.config.enable_phase_2 = 1
		self.config.cost_basis = "Latest Submitted Purchase Invoice"
		self.locations = ModuleType(PREFIX + "locations")
		self.locations.branch_for = Mock(return_value="BR")
		self.locations.resolve = Mock(return_value=None)
		self.policies = ModuleType(PREFIX + "policies")
		self.policies.check_filters = Mock()
		self.policies.groups = Mock(return_value=["Leaf", "Parent"])
		self.costs = ModuleType(PREFIX + "cost_sources")
		self.costs.cost = Mock(
			return_value={
				"cost_rate": 1000,
				"supplier": "SUP",
				"cost_source": "Latest Submitted Purchase Invoice",
				"source_doctype": "Purchase Invoice",
				"source_document": "PI-1",
				"cost_modified": "first",
			}
		)
		self.modules = {
			PREFIX + "locations": self.locations,
			PREFIX + "policies": self.policies,
			PREFIX + "cost_sources": self.costs,
		}

	def calculate(self):
		with patch.dict("sys.modules", self.modules):
			return self.engine.calculate_row(self.config, self.policy, self.context)

	def test_evidence_supplier_selects_supplier_rule_and_keeps_trace(self):
		self.store.rules_for.return_value = [
			Row(
				name="SUP-RULE",
				supplier="SUP",
				calculation_mode="Override",
				calculation_method="Markup Percentage",
				calculation_value=35,
			)
		]
		row = self.calculate()
		self.assertEqual(row["proposed_rate"], 1350)
		self.assertEqual(row["pricing_rule"], "SUP-RULE")
		self.assertEqual(row["source_document"], "PI-1")
		self.assertEqual(row["branch"], "BR")

	def test_use_default_inherits_lower_rule_and_zero_is_explicit(self):
		self.store.rules_for.return_value = [
			Row(
				name="ITEM",
				item_code="I",
				calculation_mode="Override",
				calculation_method="Markup Percentage",
				calculation_value=40,
			),
			Row(name="SUP-ITEM", item_code="I", supplier="SUP", calculation_mode="Use Default"),
		]
		self.assertEqual(self.calculate()["proposed_rate"], 1400)
		self.store.rules_for.return_value[1].update(
			calculation_mode="Override", calculation_method="Markup Percentage", calculation_value=0
		)
		self.assertEqual(self.calculate()["proposed_rate"], 1000)
		self.assertEqual(self.calculate()["result"], "Blocked")

	def test_rule_cost_override_keeps_evidence_supplier(self):
		self.store.rules_for.return_value = [
			Row(name="Supplier", supplier="SUP", cost_basis="Latest Submitted Purchase Receipt")
		]
		self.calculate()
		self.assertEqual(self.costs.cost.call_count, 2)
		self.assertEqual(self.costs.cost.call_args.args[5], "Latest Submitted Purchase Receipt")
		self.assertEqual(self.costs.cost.call_args.args[6]["supplier"], "SUP")

	def test_evidence_change_changes_publication_fingerprint(self):
		first = self.calculate()
		self.costs.cost.return_value["cost_modified"] = "changed"
		self.assertNotEqual(first["calculation_hash"], self.calculate()["calculation_hash"])

	def test_phase_one_path_remains_unchanged_when_opt_in_is_off(self):
		self.config.enable_phase_2 = 0
		self.calculate()
		self.store.purchase_cost.assert_called_once()
		self.costs.cost.assert_not_called()

	def test_retain_price_decreases_uses_branch_fallback_rate(self):
		self.locations.resolve.return_value = {
			"rate": 1700,
			"source": "BR-PRICE",
			"price_list": "Retail",
			"resolution": "Branch",
		}
		row = self.calculate()
		self.assertEqual(row["proposed_rate"], 1700)
		self.assertEqual(row["previous_rate"], 1700)
		self.assertEqual(row["price_source"], "Retained Current Price")


class TestCostEvidence(unittest.TestCase):
	def setUp(self):
		self.f = make_frappe()
		self.repo = ModuleType(PREFIX + "repository")
		self.repo.exchange_rate = Mock(return_value=(Decimal(2), "FX-1"))
		self.repo.uom_factor = Mock(return_value=Decimal(10))
		self.m = load("cost_sources", self.f, {PREFIX + "repository": self.repo})
		self.item = Row(name="ITEM", stock_uom="Nos")
		self.doc = SimpleNamespace(
			name="PI-1",
			company="C",
			supplier="SUP",
			docstatus=1,
			is_return=0,
			posting_date="2026-11-01",
			creation="2026-11-01 12:00:00",
			modified="2026-11-02",
			check_permission=Mock(),
			items=[Row(name="LINE", item_code="ITEM", idx=1, base_net_amount=1000, stock_qty=4)],
		)
		self.f.get_list.return_value = [Row(name="PI-1")]
		self.f.get_doc.return_value = self.doc

	def test_receipt_cost_is_normalized_and_links_receipt_evidence(self):
		row = self.m.submitted(
			"C",
			self.item,
			"Box",
			"TZS",
			"2026-11-03",
			"Purchase Receipt",
			{"supplier": "SUP", "source_document": "PI-1"},
			current=True,
			lock=True,
		)
		self.assertEqual(row["cost_rate"], 5000)
		self.assertEqual(row["source_doctype"], "Purchase Receipt")
		self.assertIsNone(row["source_invoice"])
		self.assertEqual(row["source_detail"], "LINE")
		self.f.get_doc.assert_called_once_with("Purchase Receipt", "PI-1", for_update=True)
		criteria = self.f.get_list.call_args.kwargs["filters"]
		self.assertIn(["Purchase Receipt", "docstatus", "=", 1], criteria)
		self.assertIn(["Purchase Receipt", "supplier", "=", "SUP"], criteria)

	def test_changed_company_supplier_return_or_date_is_rejected(self):
		for field, value in (
			("company", "OTHER"),
			("supplier", "OTHER"),
			("is_return", 1),
			("docstatus", 2),
			("posting_date", "2026-12-01"),
		):
			original = getattr(self.doc, field)
			setattr(self.doc, field, value)
			with self.assertRaisesRegex(ValueError, "changed"):
				self.m.submitted(
					"C", self.item, "Nos", "TZS", "2026-11-03", "Purchase Invoice", {"supplier": "SUP"}
				)
			setattr(self.doc, field, original)

	def test_supplier_source_requires_supplier_and_current_source_requires_reference(self):
		for basis in ("Supplier Latest Purchase Rate", "Current Purchase Invoice"):
			row = self.m.cost("C", self.item, "Nos", "TZS", "2026-11-03", basis, {})
			self.assertIsNone(row["cost_rate"])
			self.assertTrue(row["cost_reason"])

	def test_fallback_is_ordered_and_only_when_configured(self):
		with patch.object(self.m, "submitted", side_effect=[{"cost_rate": None}, {"cost_rate": 250}]):
			row = self.m.cost(
				"C",
				self.item,
				"Nos",
				"TZS",
				"2026-11-03",
				"Latest Submitted Purchase Invoice",
				{},
				fallbacks="Latest Submitted Purchase Receipt",
			)
		self.assertEqual(row["cost_rate"], 250)
		self.assertEqual(row["cost_source"], "Latest Submitted Purchase Receipt")
		with patch.object(self.m, "submitted", return_value={"cost_rate": None}) as submitted:
			self.m.cost("C", self.item, "Nos", "TZS", "2026-11-03", "Latest Submitted Purchase Invoice", {})
			submitted.assert_called_once()

	def test_permissions_fail_without_falling_back(self):
		self.f.has_permission.side_effect = PermissionError("denied")
		with self.assertRaises(PermissionError):
			self.m.cost(
				"C",
				self.item,
				"Nos",
				"TZS",
				"2026-11-03",
				"Latest Submitted Purchase Invoice",
				{},
				fallbacks="Latest Submitted Purchase Receipt",
			)

	def test_valuation_is_dated_and_requires_warehouse(self):
		with self.assertRaisesRegex(ValueError, "Warehouse"):
			self.m.valuation("C", self.item, "Nos", "TZS", "2026-11-03", None)
		self.f.get_doc.return_value = SimpleNamespace(
			name="SLE-1",
			company="C",
			warehouse="WH",
			item_code="ITEM",
			is_cancelled=0,
			posting_date="2026-11-03",
			posting_datetime="2026-11-03 14:00:00",
			valuation_rate=25,
			modified="2026-11-03",
			voucher_detail_no="LINE",
			check_permission=Mock(),
		)
		row = self.m.valuation("C", self.item, "Box", "TZS", "2026-11-03", "WH", lock=True)
		self.assertEqual(row["cost_rate"], 500)
		self.assertEqual(row["source_doctype"], "Stock Ledger Entry")
		self.assertEqual(self.f.get_list.call_args.kwargs["filters"]["posting_datetime"], ["<", "2026-11-04"])
		self.assertEqual(self.f.get_list.call_args.kwargs["filters"]["is_cancelled"], 0)


class TestBranchAndRuntimeFallback(unittest.TestCase):
	def setUp(self):
		self.f, self.access = make_frappe(), access_stub()
		self.access.check_link = Mock()
		self.repo = ModuleType(PREFIX + "repository")
		self.repo.price_rows = Mock(return_value=[])
		self.repo.valid_price = Mock(side_effect=lambda rows, date: rows[0] if rows else None)
		self.repo.standard_price = Mock(return_value=None)
		self.f.get_cached_doc = Mock(return_value=Row(name="Base", enabled=1, selling=1, currency="TZS"))
		self.f.get_cached_value.side_effect = lambda dt, name, field: (
			"BR" if field == "custom_spe_branch" else "TZS"
		)
		self.f.db.get_value = Mock(return_value=None)
		self.m = load("locations", self.f, {PREFIX + "repository": self.repo, PREFIX + "access": self.access})

	def resolve(self):
		return self.m.resolve("C", "Retail", Row(name="ITEM"), "Nos", "2026-11-03", "WH")

	def test_warehouse_then_branch_then_standard_precedence(self):
		warehouse = Row(name="Warehouse Price", rate=10, currency="TZS")
		branch = Row(name="Branch Price", rate=20, currency="TZS")
		self.repo.price_rows.side_effect = [[warehouse], [branch]]
		self.assertEqual(self.resolve()["source"], "Warehouse Price")
		self.repo.price_rows.side_effect = [[], [branch]]
		self.assertEqual(self.resolve()["resolution"], "Branch")
		self.repo.price_rows.side_effect = [[], []]
		self.repo.standard_price.return_value = Row(price_list_rate=30)
		self.assertEqual(self.resolve()["resolution"], "Standard")

	def test_cross_branch_mapping_is_rejected(self):
		with self.assertRaisesRegex(ValueError, "does not belong"):
			self.m.branch_for("C", "WH", "Other Branch")

	def test_alternate_list_requires_opt_in_and_returns_real_source(self):
		def policy(dt, criteria, fields, **kwargs):
			if isinstance(fields, list) and criteria["price_list"] == "Retail":
				return Row(runtime_fallback=1, fallback_price_list="Base")
			return None

		self.f.db.get_value.side_effect = policy
		self.repo.standard_price.side_effect = lambda company, price_list, *a: (
			Row(price_list_rate=42) if price_list == "Base" else None
		)
		result = self.resolve()
		self.assertEqual(result["rate"], 42)
		self.assertEqual(result["price_list"], "Base")
		self.assertEqual(result["resolution"], "Alternate List / Standard")
		self.f.db.get_value.side_effect = None
		self.f.db.get_value.return_value = Row(runtime_fallback=0, fallback_price_list="Base")
		self.assertIsNone(self.resolve())

	def test_fallback_cycle_and_currency_mismatch_fail_explicitly(self):
		self.f.db.get_value.side_effect = lambda dt, criteria, fields, **kwargs: (
			Row(runtime_fallback=1, fallback_price_list="Retail") if isinstance(fields, list) else None
		)
		self.f.get_cached_doc.return_value.name = "Retail"
		with self.assertRaisesRegex(ValueError, "Cyclic"):
			self.resolve()
		self.f.get_cached_doc.return_value.currency = "USD"
		with self.assertRaisesRegex(ValueError, "same-currency"):
			self.resolve()


if __name__ == "__main__":
	unittest.main()
