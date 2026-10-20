"""Isolated unit tests; run with python -m unittest av_tools.asset_reconciliation.test_reconciliation.

The module loader supplies a minimal Frappe double only to the modules under test.
It neither needs a bench nor alters an installed site's global Frappe module.
"""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value


class Field:
	def __init__(self, name):
		self.name = name

	def __eq__(self, value):
		return lambda row: row.get(self.name) == value

	def __ne__(self, value):
		return lambda row: row.get(self.name) != value

	def __le__(self, value):
		return lambda row: row.get(self.name) is not None and row.get(self.name) <= value

	def isin(self, values):
		return lambda row: row.get(self.name) in values


class Table:
	def __init__(self, doctype):
		self.doctype = doctype

	def __getattr__(self, name):
		return Field(name)


class Query:
	def __init__(self, table, data):
		self.table = table
		self.data = data
		self.predicates = []

	def select(self, *args):
		return self

	def join(self, *args):
		return self

	def on(self, *args):
		return self

	def where(self, predicate):
		self.predicates.append(predicate)
		return self

	def run(self, **kwargs):
		return [r for r in self.data.get(self.table.doctype, []) if all(p(r) for p in self.predicates)]


def load_module(path, frappe, extra=None):
	utils = ModuleType("frappe.utils")
	utils.flt = lambda value: float(value or 0)
	document = ModuleType("frappe.model.document")
	document.Document = Row
	modules = {"frappe": frappe, "frappe.utils": utils, "frappe.model.document": document}
	modules.update(extra or {})
	spec = importlib.util.spec_from_file_location("isolated_" + Path(path).stem, ROOT / path)
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, modules):
		spec.loader.exec_module(module)
	return module


class TestReconciliation(unittest.TestCase):
	def setUp(self):
		self.data = {}
		self.frappe = ModuleType("frappe")
		self.frappe._dict = Row
		self.frappe.whitelist = lambda: lambda f: f
		self.frappe.read_only = lambda: lambda f: f
		self.frappe.throw = Mock(side_effect=ValueError)
		self.frappe.get_doc = Mock(return_value=Mock(company="ACME", docstatus=1))
		self.frappe.get_cached_value = Mock(return_value="TZS")
		self.frappe.has_permission = Mock(return_value=True)
		self.frappe.get_list = Mock(return_value=[])
		self.frappe.get_meta = Mock(
			return_value=Mock(get_permitted_fieldnames=lambda **kwargs: "asset allocated_amount".split())
		)
		self.frappe.PermissionError = PermissionError
		self.frappe.utils = SimpleNamespace(today=lambda: "2026-10-18")
		self.frappe.qb = SimpleNamespace(DocType=Table, from_=lambda table: Query(table, self.data))

	def report(self, view="All Records"):
		permissions = ModuleType("av_tools.asset_reconciliation.permissions")
		permissions.run_permitted = lambda query, doctype, cache, **kwargs: query.run(as_dict=True)
		module = load_module(
			"av_tools/report/fixed_asset_financial_reconciliation/fixed_asset_financial_reconciliation.py",
			self.frappe,
			{permissions.__name__: permissions},
		)
		with patch.object(self.frappe, "get_doc", return_value=Mock(company="ACME", is_group=1, lft=1, rgt=10)):
\t\t\twith patch.object(self.frappe, "get_list", return_value=["Depreciation Expense - A"]):
\t\t\t\treturn module.execute(
\t\t\t\t\t{"company": "ACME", "as_on": "2026-10-18", "view_mode": view, "depreciation_group_account": "Depreciation - A"}
\t\t\t\t)[1]

	def asset(self, **kwargs):
		row = Row(
			name="AST-1",
			company="ACME",
			docstatus=1,
			status="Submitted",
			total_asset_cost=100,
			calculate_depreciation=0,
			asset_category="Equipment",
			purchase_date="2026-01-01",
		)
		row.update(kwargs)
		self.data["Asset"] = [row]
		self.data["Asset Category"] = [
			Row(name="Equipment", company_name="ACME", fixed_asset_account="Equipment - A")
		]

	def controller(self, **kwargs):
		module = load_module(
			"av_tools/doctype/asset_capitalization_reconciliation/asset_capitalization_reconciliation.py",
			self.frappe,
		)
		doc = module.AssetCapitalizationReconciliation(
			company="ACME", status="Approved", assets=[], sources=[]
		)
		doc.update(kwargs)
		return doc

	def test_approval_rejects_imbalance_and_computes_totals_on_server(self):
		doc = self.controller(
			assets=[Row(asset="AST-1", allocated_amount=100)],
			sources=[Row(source_voucher_type="Journal Entry", source_voucher="JE-1", allocated_amount=90)],
		)
		with self.assertRaises(ValueError):
			doc.validate()
		self.assertEqual(doc.variance, 10)

	def test_company_and_voucher_line_are_validated(self):
		doc = self.controller(
			assets=[Row(asset="AST-1", allocated_amount=100)],
			sources=[
				Row(
					source_voucher_type="Journal Entry",
					source_voucher="JE-1",
					source_line="other",
					allocated_amount=100,
				)
			],
		)
		voucher = Row(company="ACME", docstatus=1, accounts=[Row(name="correct")])
		voucher.check_permission = Mock()
		self.frappe.get_doc.return_value = voucher
		with self.assertRaises(ValueError):
			doc.validate()
		voucher.company = "OTHER"
		with self.assertRaises(ValueError):
			doc.check_reference("Asset", "AST-1")

	def test_derived_connections_are_reset_when_voucher_changes(self):
		row = Row(
			source_voucher_type="Journal Entry",
			source_voucher="JE-1",
			allocated_amount=100,
			reconciliation_purchase_invoice="PI-OLD",
		)
		doc = self.controller(assets=[Row(asset="AST-1", allocated_amount=100)], sources=[row])
		doc.validate()
		self.assertEqual(row.reconciliation_journal_entry, "JE-1")
		self.assertIsNone(row.reconciliation_purchase_invoice)

	def test_non_depreciating_asset_with_no_acquisition_support_remains_visible(self):
		self.asset()
		rows = self.report("Exceptions Only")
		self.assertEqual(rows[0]["unmapped_cost"], 100)

	def test_direct_submitted_invoice_item_covers_asset_cost(self):
		self.asset(purchase_invoice="PI-1", purchase_invoice_item="ITEM-1")
		self.data["Purchase Invoice"] = [Row(name="PI-1", docstatus=1)]
		self.data["Purchase Invoice Item"] = [
			Row(name="ITEM-1", parent="PI-1", expense_account="Equipment - A", base_net_amount=100, qty=1)
		]
		self.assertEqual(self.report()[0]["mapped_cost"], 100)
		self.assertEqual(self.report("Exceptions Only"), [])

	def test_generated_source_links_cover_multiple_assets_without_multiplying_invoice_cost(self):
		self.asset(
			av_nta_purchase_invoice="PI-1",
			av_nta_purchase_invoice_item="ITEM-1",
			total_asset_cost=50,
			asset_quantity=1,
		)
		second = Row(self.data["Asset"][0])
		second.name = "AST-2"
		self.data["Asset"].append(second)
		self.data["Purchase Invoice"] = [Row(name="PI-1", docstatus=1)]
		self.data["Purchase Invoice Item"] = [
			Row(name="ITEM-1", parent="PI-1", expense_account="Equipment - A", base_net_amount=100, qty=2)
		]
		rows = self.report()
		self.assertEqual(sum(row["mapped_cost"] for row in rows), 100)
		self.assertTrue(all(row["purchase_invoice"] == "PI-1" for row in rows))

	def test_scrapped_asset_and_scrap_journal_are_excluded(self):
		self.asset(status="Scrapped", journal_entry_for_scrap="JE-SCRAP")
		self.data["GL Entry"] = [
			Row(
				company="ACME",
				posting_date="2026-01-01",
				is_cancelled=0,
				voucher_type="Journal Entry",
				voucher_no="JE-SCRAP",
				account="Equipment - A",
				debit=0,
				credit=100,
			)
		]
		self.assertEqual(self.report(), [])

	def test_balanced_approved_mapping_covers_asset(self):
		self.asset()
		self.data["Asset Capitalization Reconciliation"] = [
			Row(name="REC-1", company="ACME", status="Approved")
		]
		self.data["Asset Reconciliation Asset"] = [Row(parent="REC-1", asset="AST-1", allocated_amount=100)]
		self.data["Asset Reconciliation Source"] = [
			Row(
				parent="REC-1",
				source_voucher_type="Journal Entry",
				source_voucher="JE-1",
				allocated_amount=100,
			)
		]
		rows = self.report()
		self.assertEqual(rows[0]["mapped_cost"], 100)
		self.assertEqual(rows[0]["reconciliation"], "REC-1")
		self.assertEqual(self.report("Exceptions Only"), [])

	def test_audit_checks_asset_and_gl_permissions_and_limits_results(self):
		api = load_module("asset_reconciliation/api.py", self.frappe)
		self.frappe.get_meta.return_value.get_permitted_fieldnames = (
			lambda: "asset_name status total_asset_cost value_after_depreciation journal_entry_for_scrap company".split()
		)
		asset = Row(name="AST-1", company="ACME")
		asset.check_permission = Mock()
		self.frappe.get_doc.return_value = asset
		self.frappe.get_list.return_value = [Row(debit=2, credit=1)] * 501
		result = api.asset_accounting_audit("AST-1")
		asset.check_permission.assert_called_once_with("read")
		self.assertTrue(result["truncated"])
		self.assertEqual(result["total_debit"], 1000)
		self.assertEqual(self.frappe.get_list.call_args.kwargs["filters"]["against_voucher_type"], "Asset")
		self.frappe.has_permission.side_effect = PermissionError
		with self.assertRaises(PermissionError):
			api.asset_accounting_audit("AST-1")

	def test_links_use_permission_filtered_parent_query_without_500_cap(self):
		api = load_module("asset_reconciliation/api.py", self.frappe)
		api.asset_capitalization_reconciliation_links("Journal Entry", "JE-1")
		self.assertEqual(self.frappe.get_list.call_args.args[0], "Asset Capitalization Reconciliation")
		self.assertEqual(self.frappe.get_list.call_args.kwargs["limit_page_length"], 0)
		with self.assertRaises(ValueError):
			api.asset_capitalization_reconciliation_links("User", "Administrator")

	def test_query_permission_cache_and_child_parent_boundary(self):
		permissions = load_module("asset_reconciliation/permissions.py", self.frappe)
		self.frappe.get_list.return_value = ["REC-1"]
		self.data["Asset Reconciliation Asset"] = [
			Row(parent="REC-1", parenttype="Asset Capitalization Reconciliation", parentfield="assets"),
			Row(parent="REC-2", parenttype="Asset Capitalization Reconciliation", parentfield="assets"),
		]
		cache = {}
		query = self.frappe.qb.from_(Table("Asset Reconciliation Asset"))
		self.assertEqual(len(permissions.run_permitted(query, "Asset Reconciliation Asset", cache)), 1)
		permissions.permitted_names("Asset Capitalization Reconciliation", cache)
		self.frappe.get_list.assert_called_once()
		self.frappe.has_permission.side_effect = PermissionError
		with self.assertRaises(PermissionError):
			permissions.permitted_names("GL Entry", {})

	def test_dashboard_hooks_preserve_and_do_not_duplicate_connections(self):
		dashboard = load_module("asset_reconciliation/dashboard.py", self.frappe)
		existing = {
			"transactions": [{"label": "Existing", "items": ["Payment Entry"]}],
			"non_standard_fieldnames": {"Payment Entry": "reference_name"},
			"internal_links": {"Asset": "asset"},
		}
		result = dashboard.purchase_invoice(existing)
		self.assertEqual(existing["transactions"][0]["items"], ["Payment Entry"])
		self.assertEqual(result["internal_links"], existing["internal_links"])
		self.assertEqual(result["non_standard_fieldnames"]["Payment Entry"], "reference_name")
		self.assertEqual(dashboard.purchase_invoice(result), result)

	def test_report_fails_closed_on_restricted_accounting_field(self):
		permissions = load_module("asset_reconciliation/permissions.py", self.frappe)
		self.frappe.get_meta.return_value.get_permitted_fieldnames = lambda **kwargs: ["debit"]
		with self.assertRaises(ValueError):
			permissions.run_permitted(self.frappe.qb.from_(Table("GL Entry")), "GL Entry", {})

	def test_migration_is_idempotent_and_only_updates_derived_child_fields(self):
		prepare = ModuleType("av_tools.patches.v1_0.prepare_asset_reconciliation")
		prepare.DOCTYPES = (
			"Asset Reconciliation Asset",
			"Asset Reconciliation Source",
			"Asset Capitalization Reconciliation",
		)
		migration = load_module(
			"patches/v1_0/migrate_asset_reconciliation.py", self.frappe, {prepare.__name__: prepare}
		)
		rows = [
			Row(
				name="ROW-1",
				source_voucher_type="Purchase Invoice",
				source_voucher="PI-1",
				allocated_amount=125,
			)
		]
		state = {}

		def set_value(doctype, name, field, value=None, **kwargs):
			changes = field if isinstance(field, dict) else {field: value}
			state.setdefault((doctype, name), {}).update(changes)

		self.frappe.db = Mock()
		self.frappe.db.exists.return_value = True
		self.frappe.db.set_value.side_effect = set_value
		self.frappe.get_all = Mock(return_value=rows)
		self.frappe.reload_doc = Mock()
		self.frappe.clear_cache = Mock()
		self.frappe.scrub = lambda value: value.lower().replace(" ", "_")
		migration.execute()
		first_state = {key: dict(value) for key, value in state.items()}
		migration.execute()
		self.assertEqual(state, first_state)
		self.assertEqual(
			state[("Asset Reconciliation Source", "ROW-1")],
			{"reconciliation_purchase_invoice": "PI-1", "reconciliation_journal_entry": None},
		)
		self.assertEqual(rows[0].allocated_amount, 125)
		self.frappe.db.delete.assert_not_called()
		self.assertFalse(
			any(doctype in ("Asset", "GL Entry", "Journal Entry", "Purchase Invoice") for doctype, _ in state)
		)
		self.assertTrue(
			all(state[("Client Script", name)]["enabled"] == 0 for name in migration.CLIENT_SCRIPTS)
		)

	def test_unbalanced_mapping_does_not_cover_cost(self):
		self.asset()
		self.data["Asset Capitalization Reconciliation"] = [
			Row(name="REC-1", company="ACME", status="Approved")
		]
		self.data["Asset Reconciliation Asset"] = [Row(parent="REC-1", asset="AST-1", allocated_amount=100)]
		self.data["Asset Reconciliation Source"] = [Row(parent="REC-1", allocated_amount=50)]
		self.assertEqual(self.report()[0]["mapped_cost"], 0)

	def test_prepare_preserves_legacy_roles_and_permissions_without_touching_allocations(self):
		permissions = ModuleType("frappe.permissions")
		permissions.setup_custom_perms = Mock()
		self.frappe.db = Mock()
		self.frappe.db.exists.side_effect = lambda doctype, name: doctype != "Custom Role"
		self.frappe.db.get_value.side_effect = lambda doctype, name, field: "No" if doctype == "Report" else 1
		self.frappe.get_all = Mock(return_value=["Accounts User", "Office Admin"])
		self.frappe.clear_cache = Mock()
		prepare = load_module(
			"patches/v1_0/prepare_asset_reconciliation.py", self.frappe, {"frappe.permissions": permissions}
		)
		prepare.execute()
		permissions.setup_custom_perms.assert_called_once_with("Asset Capitalization Reconciliation")
		role_data = self.frappe.get_doc.call_args.args[0]
		self.assertEqual(role_data["roles"], [{"role": "Accounts User"}, {"role": "Office Admin"}])
		self.assertTrue(all(call.args[0] == "DocType" for call in self.frappe.db.set_value.call_args_list))


if __name__ == "__main__":
	unittest.main()
