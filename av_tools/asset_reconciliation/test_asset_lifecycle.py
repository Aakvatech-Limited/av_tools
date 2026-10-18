"""Isolated tests for creation and destructive cleanup boundaries; no site writes."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent


class Doc(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)

	def set(self, key, value):
		setattr(self, key, value)


def load(name, frappe):
	utils = ModuleType("frappe.utils")
	utils.flt = lambda value: float(value or 0)
	utils.cint = lambda value: int(value or 0)
	accounts = ModuleType("erpnext.accounts.utils")
	accounts.get_fiscal_year = Mock(
		return_value=Doc(year_start_date="2026-07-01", year_end_date="2027-06-30")
	)
	dimensions = ModuleType("erpnext.accounts.doctype.accounting_dimension.accounting_dimension")
	dimensions.get_dimensions = lambda **kwargs: ([{"fieldname": "cost_center"}], {})
	modules = {
		"frappe": frappe,
		"frappe.utils": utils,
		"erpnext.accounts.utils": accounts,
		dimensions.__name__: dimensions,
	}
	spec = importlib.util.spec_from_file_location("isolated_" + name, ROOT / (name + ".py"))
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, modules):
		spec.loader.exec_module(module)
	return module


class TestPurchaseAssets(unittest.TestCase):
	def setUp(self):
		self.f = ModuleType("frappe")
		self.f._ = lambda text: text
		self.f.throw = Mock(side_effect=ValueError)
		self.f.has_permission = Mock(return_value=True)
		self.f.msgprint = Mock()
		self.f.db = Mock()
		self.f.db.exists.return_value = False
		self.f.db.get_single_value.return_value = 2
		self.f.db.get_value.return_value = None
		self.settings = Doc(
			enable_no_time_appropriation_assets=1,
			nta_depreciation_method="Straight Line",
			nta_depreciation_frequency=12,
			nta_depreciation_duration_years=5,
		)
		self.item = Doc(
			name="LAPTOP",
			item_name="Laptop",
			is_fixed_asset=1,
			disabled=0,
			is_stock_item=0,
			asset_category="Equipment",
			asset_naming_series=None,
		)
		self.f.get_cached_doc = (
			lambda doctype, *args: self.settings if doctype == "AV Tools Settings" else self.item
		)
		self.f.get_cached_value = lambda doctype, *args: 1 if doctype == "AV Tools Settings" else None
		self.inserted = []

		def get_doc(data):
			doc = Doc(**data)

			def insert():
				doc.name = f"AST-{len(self.inserted) + 1}"
				self.inserted.append(doc)
				return doc

			doc.insert = insert
			return doc

		self.f.get_doc = get_doc
		self.module = load("purchase_assets", self.f)
		self.row = Doc(
			name="LINE-1",
			idx=1,
			item_code="LAPTOP",
			item_name="Laptop",
			qty=3,
			base_net_amount=100,
			valuation_rate=0,
			asset_location="HQ",
			cost_center="Main",
		)
		self.invoice = Doc(
			name="PI-1",
			docstatus=1,
			is_return=0,
			company="ACME",
			supplier="Supplier",
			posting_date="2026-10-18",
			items=[self.row],
			check_permission=Mock(),
		)

	def test_creates_one_validated_draft_per_quantity_with_non_calendar_fiscal_dates(self):
		result = self.module.create_draft_assets(self.invoice)
		self.assertEqual(len(result), 3)
		self.assertEqual(sum(asset.net_purchase_amount for asset in self.inserted), 100)
		for asset in self.inserted:
			self.assertEqual(asset.docstatus, 0)
			self.assertEqual(asset.asset_type, "Existing Asset")
			self.assertFalse(asset.get("purchase_invoice"))
			self.assertEqual(asset.av_nta_purchase_invoice_item, "LINE-1")
			self.assertEqual(asset.purchase_date, "2026-07-01")
			self.assertEqual(asset.available_for_use_date, "2026-07-01")
			self.assertEqual(asset.finance_books[0]["depreciation_start_date"], "2027-06-30")
			self.assertEqual(asset.finance_books[0]["total_number_of_depreciations"], 5)
			self.assertEqual(asset.cost_center, "Main")

	def test_repeated_item_lines_have_distinct_unit_keys(self):
		second = Doc(**vars(self.row))
		second.name = "LINE-2"
		second.qty = 1
		second.base_net_amount = 25
		self.invoice.items.append(second)
		self.module.create_draft_assets(self.invoice)
		self.assertEqual(len({asset.av_nta_unit_key for asset in self.inserted}), 4)

	def test_hook_replay_does_not_duplicate_assets(self):
		self.module.create_draft_assets(self.invoice)
		keys = {asset.av_nta_unit_key: Doc(name=asset.name, docstatus=0) for asset in self.inserted}
		self.f.db.get_value.side_effect = (
			lambda doctype, filters, *args, **kwargs: keys.get(filters.get("av_nta_unit_key"))
			if isinstance(filters, dict)
			else None
		)
		self.assertEqual(self.module.create_draft_assets(self.invoice), [])
		self.assertEqual(len(self.inserted), 3)

	def test_disabled_returns_and_non_fixed_items_create_nothing(self):
		with patch.object(self.module, "enabled", return_value=False):
			self.assertEqual(self.module.create_draft_assets(self.invoice), [])
		self.invoice.is_return = 1
		self.assertEqual(self.module.create_draft_assets(self.invoice), [])
		self.invoice.is_return = 0
		self.item.is_fixed_asset = 0
		self.assertEqual(self.module.create_draft_assets(self.invoice), [])

	def test_fractional_quantity_and_missing_location_are_rejected(self):
		self.row.qty = 1.5
		with self.assertRaises(ValueError):
			self.module.create_draft_assets(self.invoice)
		self.row.qty = 1
		self.row.asset_location = None
		with self.assertRaises(ValueError):
			self.module.create_draft_assets(self.invoice)
		self.assertEqual(self.inserted, [])

	def test_native_or_receipt_assets_block_duplicate_creation(self):
		self.f.db.exists.return_value = True
		with self.assertRaises(ValueError):
			self.module.create_draft_assets(self.invoice)
		self.assertEqual(self.inserted, [])

	def test_create_permission_failure_is_not_bypassed(self):
		self.f.has_permission.side_effect = PermissionError
		with self.assertRaises(PermissionError):
			self.module.create_draft_assets(self.invoice)
		self.assertEqual(self.inserted, [])

	def test_non_depreciable_category_and_valuation_cost(self):
		self.f.get_cached_value = (
			lambda doctype, *args: 1 if doctype in ("Asset Category", "AV Tools Settings") else None
		)
		self.row.valuation_rate = 40
		self.module.create_draft_assets(self.invoice)
		self.assertEqual(sum(asset.net_purchase_amount for asset in self.inserted), 120)
		self.assertTrue(all(not asset.calculate_depreciation for asset in self.inserted))

	def test_settings_duration_and_written_down_rate_validation(self):
		self.settings.nta_depreciation_frequency = 7
		with self.assertRaises(ValueError):
			self.module.validate_settings(self.settings)
		self.settings.nta_depreciation_frequency = 12
		self.settings.nta_depreciation_method = "Written Down Value"
		with self.assertRaises(ValueError):
			self.module.validate_settings(self.settings)
		self.settings.nta_depreciation_rate = 20
		self.module.validate_settings(self.settings)

	def test_mixin_preserves_native_behavior_only_when_disabled(self):
		native = Mock()

		class Base:
			def get(self, key):
				return 0

			def process_fixed_asset(self):
				native()

		class Invoice(self.module.NoTimeAppropriationPurchaseInvoice, Base):
			pass

		Invoice().process_fixed_asset()
		native.assert_not_called()
		with patch.object(self.module, "enabled", return_value=False):
			Invoice().process_fixed_asset()
		native.assert_called_once()

	def test_invoice_cancellation_preflights_all_assets_even_when_setting_is_disabled(self):
		cleanup = ModuleType("av_tools.asset_reconciliation.asset_cleanup")
		cleanup.build_plan = Mock(
			side_effect=[
				{"asset": "AST-1", "blockers": []},
				{"asset": "AST-2", "blockers": ["shared movement"]},
			]
		)
		cleanup.execute_plan = Mock()
		self.f.get_all = Mock(return_value=["AST-1", "AST-2"])
		with (
			patch.dict(sys.modules, {cleanup.__name__: cleanup}),
			patch.object(self.module, "enabled", return_value=False),
		):
			with self.assertRaises(ValueError):
				self.module.cancel_invoice_assets(self.invoice)
		cleanup.execute_plan.assert_not_called()

	def test_invoice_cancellation_runs_owned_cleanup_and_propagates_failures(self):
		cleanup = ModuleType("av_tools.asset_reconciliation.asset_cleanup")
		cleanup.build_plan = Mock(return_value={"asset": "AST-1", "blockers": []})
		cleanup.execute_plan = Mock(side_effect=PermissionError)
		self.f.get_all = Mock(return_value=["AST-1"])
		with patch.dict(sys.modules, {cleanup.__name__: cleanup}):
			with self.assertRaises(PermissionError):
				self.module.cancel_invoice_assets(self.invoice)
		cleanup.execute_plan.assert_called_once()
		self.f.db.commit.assert_not_called()


class TestAssetCleanup(unittest.TestCase):
	def setUp(self):
		self.f = ModuleType("frappe")
		self.f._ = lambda text: text
		self.f.whitelist = lambda **kwargs: lambda method: method
		self.f.read_only = lambda: lambda method: method
		self.f.throw = Mock(side_effect=ValueError)
		self.f.session = Doc(user="manager@example.com")
		self.f.db = Mock()
		self.f.db.get_single_value.return_value = 1
		self.f.get_all = Mock(return_value=[])
		self.f.delete_doc = Mock()
		self.docs = {}
		self.f.get_doc = lambda doctype, name: self.docs[(doctype, name)]
		self.module = load("asset_cleanup", self.f)
		self.module.incoming = lambda doctype, name: set()
		self.asset = self.doc("Asset", "AST-1", company="ACME")

	def doc(self, doctype, name, docstatus=0, **kwargs):
		doc = Doc(
			doctype=doctype,
			name=name,
			docstatus=docstatus,
			modified="2026-10-18",
			check_permission=Mock(),
			cancel=Mock(),
			flags=Doc(),
			**kwargs,
		)
		self.docs[(doctype, name)] = doc
		return doc

	def test_shared_depreciation_journal_blocks_cleanup(self):
		je = self.doc(
			"Journal Entry",
			"JE-1",
			1,
			company="ACME",
			voucher_type="Depreciation Entry",
			accounts=[
				Doc(reference_type="Asset", reference_name="AST-1"),
				Doc(reference_type="Asset", reference_name="AST-2"),
			],
		)
		self.module.incoming = (
			lambda doctype, name: {("Journal Entry", je.name)} if doctype == "Asset" else set()
		)
		plan = self.module.build_plan(self.asset.name)
		self.assertTrue(plan["blockers"])
		with self.assertRaises(ValueError):
			self.module.execute_plan(plan)
		self.f.delete_doc.assert_not_called()

	def test_unrelated_purchase_document_is_never_in_delete_plan(self):
		self.doc("Purchase Invoice", "PI-1", 2, company="ACME")
		self.module.incoming = (
			lambda doctype, name: {("Purchase Invoice", "PI-1")} if doctype == "Asset" else set()
		)
		plan = self.module.build_plan(self.asset.name)
		self.assertTrue(plan["blockers"])
		self.assertFalse(any(row["doctype"] == "Purchase Invoice" for row in plan["records"]))

	def test_ledger_retention_setting_blocks_delete(self):
		self.doc("GL Entry", "GL-1", 1, voucher_type="Asset", voucher_no="AST-1", is_cancelled=0)
		self.module.incoming = lambda doctype, name: {("GL Entry", "GL-1")} if doctype == "Asset" else set()
		self.f.db.get_single_value.return_value = 0
		self.assertTrue(self.module.build_plan(self.asset.name)["blockers"])

	def test_stale_preview_and_missing_confirmation_cannot_delete(self):
		plan = self.module.build_plan(self.asset.name)
		with self.assertRaises(ValueError):
			self.module.cancel_and_delete_asset(self.asset.name, plan["token"], confirm=0)
		self.asset.modified = "changed"
		with self.assertRaises(ValueError):
			self.module.cancel_and_delete_asset(self.asset.name, plan["token"], confirm=1)
		self.f.delete_doc.assert_not_called()

	def test_permission_failure_prevents_any_cleanup(self):
		self.asset.check_permission.side_effect = PermissionError
		with self.assertRaises(PermissionError):
			self.module.build_plan(self.asset.name)
		self.f.delete_doc.assert_not_called()

	def test_cancellation_then_dependency_ordered_deletion(self):
		self.asset.docstatus = 1
		schedule = self.doc("Asset Depreciation Schedule", "S-1", 1, asset="AST-1", depreciation_schedule=[])
		journal = self.doc(
			"Journal Entry",
			"JE-1",
			1,
			company="ACME",
			voucher_type="Depreciation Entry",
			accounts=[Doc(reference_type="Asset", reference_name="AST-1")],
		)
		movement = self.doc("Asset Movement", "M-1", 1, company="ACME", assets=[Doc(asset="AST-1")])
		order = []
		for doc in (self.asset, schedule, journal, movement):

			def cancel(current=doc):
				order.append(("cancel", current.doctype))
				current.docstatus = 2

			doc.cancel.side_effect = cancel
		self.module.incoming = (
			lambda doctype, name: {
				("Asset Depreciation Schedule", "S-1"),
				("Journal Entry", "JE-1"),
				("Asset Movement", "M-1"),
			}
			if doctype == "Asset"
			else set()
		)
		self.f.delete_doc.side_effect = lambda doctype, name, **kwargs: order.append(("delete", doctype))
		plan = self.module.build_plan(self.asset.name)
		self.module.execute_plan(plan)
		self.assertLess(order.index(("cancel", "Journal Entry")), order.index(("cancel", "Asset")))
		self.assertLess(
			order.index(("delete", "Asset Depreciation Schedule")), order.index(("delete", "Journal Entry"))
		)
		self.assertEqual(order[-1], ("delete", "Asset"))
		self.assertTrue(
			all(
				not call.kwargs.get("force") and not call.kwargs.get("ignore_permissions")
				for call in self.f.delete_doc.call_args_list
			)
		)

	def test_cancellation_failure_stops_before_deletion(self):
		self.asset.docstatus = 1
		self.asset.cancel.side_effect = PermissionError
		plan = self.module.build_plan(self.asset.name)
		with self.assertRaises(PermissionError):
			self.module.execute_plan(plan)
		self.f.delete_doc.assert_not_called()
		self.f.db.commit.assert_not_called()


if __name__ == "__main__":
	unittest.main()
