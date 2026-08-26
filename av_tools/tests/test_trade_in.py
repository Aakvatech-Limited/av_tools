# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from av_tools.av_tools_hooks.trade_in import (
	create_trade_in_stock_entry,
	validate_trade_in_sales_percentage,
	validate_trade_in_serial_no_and_batch,
)
from av_tools.trade_in.utils import (
	add_trade_in_control_account,
	add_trade_in_item,
	add_trade_in_module,
	delete_trade_in_item_and_account,
)

COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"


class TestTradeIn(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_single_value("Global Defaults", "default_company", COMPANY)
		frappe.db.set_single_value("AV Tools Settings", "enable_trade_in", 1)

	def make_invoice(self, *rows, trade_in=1):
		invoice = frappe.new_doc("Sales Invoice")
		invoice.company = COMPANY
		invoice.customer = "_Test Customer"
		invoice.custom_is_trade_in = trade_in
		for row in rows:
			invoice.append("items", row)
		return invoice

	def test_setup_helpers_create_masters(self):
		add_trade_in_module()
		add_trade_in_item()
		add_trade_in_control_account()
		self.assertTrue(frappe.db.exists("Module Def", "Trade In"))
		self.assertEqual(frappe.db.get_value("Item", "Trade In", "is_stock_item"), 0)
		self.assertTrue(frappe.db.exists("Account", "Trade In Control - _TC"))
		delete_trade_in_item_and_account()
		self.assertFalse(frappe.db.exists("Account", "Trade In Control - _TC"))
		self.assertEqual(frappe.db.get_value("Item", "Trade In", "disabled"), 1)

	def test_settings_toggle_runs_setup(self):
		settings = frappe.get_single("AV Tools Settings")
		settings.enable_trade_in = 0
		settings.save()
		settings.enable_trade_in = 1
		settings.save()
		self.assertEqual(frappe.db.get_value("Item", "Trade In", "disabled"), 0)
		self.assertEqual(frappe.db.get_single_value("Selling Settings", "allow_negative_rates_for_items"), 1)

	def test_feature_flag_gate(self):
		frappe.db.set_single_value("AV Tools Settings", "enable_trade_in", 0)
		invoice = self.make_invoice(
			{"item_code": "Trade In", "qty": 1, "rate": -100, "custom_total_trade_in_value": 10**9}
		)
		self.assertIsNone(validate_trade_in_sales_percentage(invoice, "validate"))
		frappe.db.set_single_value("AV Tools Settings", "enable_trade_in", 1)
		invoice.custom_is_trade_in = 0
		self.assertIsNone(validate_trade_in_sales_percentage(invoice, "validate"))

	def test_sales_percentage_limit(self):
		add_trade_in_item()
		frappe.db.set_value("Company", COMPANY, "custom_trade_in_sales_percentage", 20)
		invoice = self.make_invoice(
			{"item_code": "_Test Item", "qty": 1, "rate": 1000, "amount": 1000},
			{
				"item_code": "Trade In",
				"qty": 1,
				"rate": -500,
				"amount": -500,
				"custom_total_trade_in_value": 500,
			},
		)
		self.assertRaises(frappe.ValidationError, validate_trade_in_sales_percentage, invoice, "validate")
		frappe.db.set_value("Company", COMPANY, "custom_trade_in_sales_percentage", 60)
		self.assertIsNone(validate_trade_in_sales_percentage(invoice, "validate"))
		no_trade = self.make_invoice({"item_code": "_Test Item", "qty": 1, "rate": 1000, "amount": 1000})
		self.assertIsNone(validate_trade_in_sales_percentage(no_trade, "validate"))

	def test_serial_and_batch_requirements(self):
		add_trade_in_item()
		serial_item = frappe.db.get_value("Item", {"has_serial_no": 1, "disabled": 0}, "name")
		batch_item = frappe.db.get_value("Item", {"has_batch_no": 1, "disabled": 0}, "name")
		self.assertTrue(serial_item and batch_item, "ERPNext test records should provide serial/batch items")

		invoice = self.make_invoice(
			{
				"item_code": "Trade In",
				"qty": 1,
				"custom_trade_in_item": serial_item,
				"custom_trade_in_qty": 2,
				"custom_trade_in_serial_no": "AV-SN-1",
			}
		)
		with self.assertRaises(frappe.ValidationError) as caught:
			validate_trade_in_serial_no_and_batch(invoice, "validate")
		self.assertIn("does not match", str(caught.exception))

		invoice = self.make_invoice(
			{"item_code": "Trade In", "qty": 1, "custom_trade_in_item": batch_item, "custom_trade_in_qty": 1}
		)
		with self.assertRaises(frappe.ValidationError) as caught:
			validate_trade_in_serial_no_and_batch(invoice, "validate")
		self.assertIn("Batch No. is mandatory", str(caught.exception))

		invoice = self.make_invoice(
			{
				"item_code": "Trade In",
				"qty": 1,
				"custom_trade_in_item": serial_item,
				"custom_trade_in_qty": 2,
				"custom_trade_in_serial_no": "AV-SN-NEW-1\nAV-SN-NEW-2",
			}
		)
		self.assertIsNone(validate_trade_in_serial_no_and_batch(invoice, "validate"))

	def test_stock_entry_created_on_submit_hook(self):
		add_trade_in_item()
		add_trade_in_control_account()
		frappe.db.set_value("Company", COMPANY, "custom_trade_in_control_account", "Trade In Control - _TC")
		frappe.db.set_value("Company", COMPANY, "custom_trade_in_sales_percentage", 100)
		invoice = self.make_invoice(
			{"item_code": "_Test Item", "qty": 1, "rate": 1000, "warehouse": WAREHOUSE},
			{
				"item_code": "Trade In",
				"qty": 1,
				"rate": -50,
				"custom_trade_in_item": "_Test Item",
				"custom_trade_in_qty": 3,
				"custom_trade_in_incoming_rate": 10,
				"custom_total_trade_in_value": 50,
				"warehouse": WAREHOUSE,
			},
		)
		invoice.insert()
		create_trade_in_stock_entry(invoice, "on_submit")
		entry = frappe.get_all(
			"Stock Entry",
			filters={"custom_sales_invoice": invoice.name},
			fields=["name", "docstatus", "stock_entry_type"],
		)
		self.assertEqual(len(entry), 1)
		self.assertEqual(entry[0].docstatus, 1)
		self.assertEqual(entry[0].stock_entry_type, "Material Receipt")
		self.assertEqual(frappe.db.get_value("Stock Entry Detail", {"parent": entry[0].name}, "qty"), 3)

	def test_stock_entry_requires_control_account(self):
		frappe.db.set_value("Company", COMPANY, "custom_trade_in_control_account", None)
		invoice = self.make_invoice(
			{
				"item_code": "Trade In",
				"qty": 1,
				"custom_trade_in_item": "_Test Item",
				"custom_trade_in_qty": 1,
			}
		)
		self.assertRaises(frappe.ValidationError, create_trade_in_stock_entry, invoice, "on_submit")
