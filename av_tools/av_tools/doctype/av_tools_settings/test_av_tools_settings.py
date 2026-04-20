import json
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.core.doctype.user.test_user import test_user
from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools.doctype.av_tools_settings.av_tools_settings import AVToolsSettings
from av_tools.av_tools_hooks.generic_erp_behavior_overrides import (
	close_or_unclose_purchase_orders,
	get_item_details,
	update_material_request_status,
	update_purchase_order_status,
)
from av_tools.patches.v1_0.migrate_generic_erp_behavior_overrides import (
	SETTINGS_DOCTYPE,
	execute as migrate_generic_settings,
)
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin
from erpnext.buying.doctype.purchase_order.test_purchase_order import create_purchase_order
from erpnext.stock.get_item_details import get_item_details as original_get_item_details


class TestAVToolsSettings(AccountsTestMixin, FrappeTestCase):
	settings_defaults = {
		"allow_reopen_of_po_based_on_role": 0,
		"role_to_reopen_po": "",
		"allow_reopen_of_material_request_based_on_role": 0,
		"role_to_reopen_material_request": "",
		"override_sales_invoice_qty": 0,
	}
	test_company_name = "Rubis Technical Services Limited"
	test_supplier_name = "AV Tools Test Supplier"
	test_customer_name = "AV Tools Test Customer"
	test_item_code = "AV Tools Test Item"
	test_price_list = "AV Tools Test Buying"
	test_price_rate = 100
	test_approval_group = "Purchase Manager"

	def setUp(self):
		frappe.set_user("Administrator")
		self.ensure_test_data()
		self.set_settings()

	def tearDown(self):
		frappe.set_user("Administrator")
		self.set_settings()
		frappe.db.rollback()
		super().tearDown()

	def test_purchase_order_status_update_allows_non_reopen_changes(self):
		po = self.make_purchase_order()

		self.set_settings(
			allow_reopen_of_po_based_on_role=1,
			role_to_reopen_po="Purchase Manager",
		)

		with self.run_as_test_user():
			update_purchase_order_status("Closed", po.name)

		po.reload()
		self.assertEqual(po.status, "Closed")

	def test_purchase_order_bulk_reopen_requires_configured_role(self):
		po = self.make_purchase_order()
		po.update_status("Closed")

		self.set_settings(
			allow_reopen_of_po_based_on_role=1,
			role_to_reopen_po="Purchase Manager",
		)

		with self.run_as_test_user():
			with self.assertRaises(frappe.ValidationError):
				close_or_unclose_purchase_orders(json.dumps([po.name]), "Submitted")

		po.reload()
		self.assertEqual(po.status, "Closed")

	def test_purchase_order_bulk_reopen_allows_configured_role(self):
		po = self.make_purchase_order()
		po.update_status("Closed")

		self.set_settings(
			allow_reopen_of_po_based_on_role=1,
			role_to_reopen_po="Purchase Manager",
		)

		with self.run_as_test_user("Purchase Manager"):
			close_or_unclose_purchase_orders(json.dumps([po.name]), "Submitted")

		po.reload()
		self.assertNotEqual(po.status, "Closed")

	def test_material_request_reopen_requires_configured_role(self):
		mr = self.make_material_request()
		mr.update_status("Stopped")

		self.set_settings(
			allow_reopen_of_material_request_based_on_role=1,
			role_to_reopen_material_request="Stock Manager",
		)

		with self.run_as_test_user():
			with self.assertRaises(frappe.ValidationError):
				update_material_request_status(mr.name, "Submitted")

		mr.reload()
		self.assertEqual(mr.status, "Stopped")

	def test_material_request_reopen_allows_configured_role(self):
		mr = self.make_material_request()
		mr.update_status("Stopped")

		self.set_settings(
			allow_reopen_of_material_request_based_on_role=1,
			role_to_reopen_material_request="Stock Manager",
		)

		with self.run_as_test_user("Stock Manager"):
			update_material_request_status(mr.name, "Submitted")

		mr.reload()
		self.assertEqual(mr.status, "Pending")

	def test_get_item_details_removes_qty_when_enabled(self):
		args = self.make_item_details_args()

		original_details = original_get_item_details(frappe._dict(args.copy()))
		self.assertIn("qty", original_details)

		self.set_settings(override_sales_invoice_qty=1)

		details = get_item_details(frappe._dict(args.copy()))

		self.assertNotIn("qty", details)
		self.assertEqual(details.get("price_list_rate"), original_details.get("price_list_rate"))

	def test_patch_migrates_settings_idempotently(self):
		expected_values = {
			"allow_reopen_of_po_based_on_role": 1,
			"role_to_reopen_po": "Purchase Manager",
			"allow_reopen_of_material_request_based_on_role": 1,
			"role_to_reopen_material_request": "Stock Manager",
			"override_sales_invoice_qty": 1,
		}

		with patch(
			"av_tools.patches.v1_0.migrate_generic_erp_behavior_overrides.source_settings_doctype_exists",
			return_value=True,
		), patch(
			"av_tools.patches.v1_0.migrate_generic_erp_behavior_overrides.get_source_values",
			return_value=expected_values,
		):
			migrate_generic_settings()
			migrate_generic_settings()

		settings = frappe.get_single(SETTINGS_DOCTYPE)
		self.assertIsInstance(settings, AVToolsSettings)

		for fieldname, value in expected_values.items():
			self.assertEqual(getattr(settings, fieldname), value)

	@contextmanager
	def run_as_test_user(self, *roles):
		with test_user(roles=["System Manager", *roles]) as user:
			frappe.set_user(user.name)
			try:
				yield user
			finally:
				frappe.set_user("Administrator")

	def set_settings(self, **overrides):
		values = {**self.settings_defaults, **overrides}
		for fieldname, value in values.items():
			frappe.db.set_single_value(SETTINGS_DOCTYPE, fieldname, value)

	def ensure_test_data(self):
		self.set_company_context()
		self.create_supplier(supplier_name=self.test_supplier_name)
		self.create_customer(customer_name=self.test_customer_name)
		self.create_item(
			item_name=self.test_item_code,
			is_stock=1,
			warehouse=self.warehouse,
			company=self.company,
		)
		self.item_uom = frappe.get_cached_value("Item", self.item, "stock_uom")
		self.company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		self.project = self.get_project()
		self.ensure_buying_price_list()
		self.ensure_item_price()

	def set_company_context(self):
		self.company = frappe.db.exists("Company", self.test_company_name)
		if not self.company:
			self.company = frappe.get_all("Company", pluck="name", limit=1)[0]

		self.cost_center = frappe.db.get_value(
			"Cost Center",
			{"company": self.company, "is_group": 0},
			"name",
		)
		self.warehouse = frappe.db.get_value(
			"Warehouse",
			{"company": self.company, "is_group": 0},
			"name",
		)
		if not self.cost_center or not self.warehouse:
			self.skipTest(f"Missing cost center or warehouse for company {self.company}")

	def get_project(self):
		project = frappe.get_all(
			"Project",
			filters={"company": self.company},
			pluck="name",
			limit=1,
		)
		if project:
			return project[0]

		self.skipTest(f"No project found for company {self.company}")

	def ensure_buying_price_list(self):
		if frappe.db.exists("Price List", self.test_price_list):
			return

		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": self.test_price_list,
				"enabled": 1,
				"buying": 1,
				"selling": 0,
				"currency": self.company_currency,
			}
		).insert()

	def ensure_item_price(self):
		existing_price = frappe.db.exists(
			"Item Price",
			{"price_list": self.test_price_list, "item_code": self.item},
		)
		if existing_price:
			frappe.db.set_value("Item Price", existing_price, "price_list_rate", self.test_price_rate)
			return

		frappe.get_doc(
			{
				"doctype": "Item Price",
				"price_list": self.test_price_list,
				"item_code": self.item,
				"price_list_rate": self.test_price_rate,
				"currency": self.company_currency,
			}
		).insert()

	def make_purchase_order(self):
		po = create_purchase_order(
			company=self.company,
			supplier=self.supplier,
			item_code=self.item,
			warehouse=self.warehouse,
			do_not_save=True,
		)
		po.set_missing_values()
		if po.meta.has_field("approval_group"):
			po.approval_group = self.test_approval_group
		if po.meta.has_field("cost_center"):
			po.cost_center = self.cost_center
		if po.meta.has_field("project"):
			po.project = self.project

		po.items[0].cost_center = self.cost_center
		if po.items[0].meta.has_field("project"):
			po.items[0].project = self.project

		po.insert()
		po.submit()
		return po

	def make_material_request(self):
		mr = frappe.new_doc("Material Request")
		mr.material_request_type = "Purchase"
		mr.company = self.company
		if mr.meta.has_field("cost_center"):
			mr.cost_center = self.cost_center
		if mr.meta.has_field("project"):
			mr.project = self.project

		item_row = {
			"item_code": self.item,
			"qty": 10,
			"uom": self.item_uom,
			"conversion_factor": 1,
			"schedule_date": frappe.utils.today(),
			"warehouse": self.warehouse,
			"cost_center": self.cost_center,
		}
		if frappe.get_meta("Material Request Item").has_field("project"):
			item_row["project"] = self.project

		mr.append("items", item_row)
		mr.insert()
		mr.submit()
		return mr

	def make_item_details_args(self):
		return {
			"item_code": self.item,
			"company": self.company,
			"conversion_rate": 1.0,
			"currency": self.company_currency,
			"price_list_currency": self.company_currency,
			"plc_conversion_rate": 1.0,
			"doctype": "Purchase Order",
			"name": None,
			"supplier": self.supplier,
			"transaction_date": None,
			"price_list": self.test_price_list,
			"is_subcontracted": 0,
			"ignore_pricing_rule": 1,
			"qty": 1,
		}
