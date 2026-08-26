# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from av_tools.api.item_lookups import (
	_collect_prices,
	get_item_info,
	get_item_prices,
	get_item_prices_custom,
	get_item_prices_custom_po,
	get_item_prices_po,
)

COMPANY = "_Test Company"
ITEM = "_Test Item"
WAREHOUSE = "_Test Warehouse - _TC"


class TestItemLookups(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext.accounts.doctype.purchase_invoice.test_purchase_invoice import make_purchase_invoice
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
		from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		make_stock_entry(item_code=ITEM, target=WAREHOUSE, qty=5, basic_rate=7, company=COMPANY)
		cls.invoice = create_sales_invoice(
			item_code=ITEM, qty=2, rate=123, company=COMPANY, customer="_Test Customer", warehouse=WAREHOUSE
		)
		cls.purchase = make_purchase_invoice(
			item_code=ITEM, qty=1, rate=77, company=COMPANY, supplier="_Test Supplier", warehouse=WAREHOUSE
		)
		cls.currency = frappe.get_cached_value("Company", COMPANY, "default_currency")

	def test_collect_prices_respects_limit(self):
		rows = [{"rate": 1}, {"rate": 0}, {"rate": 2}, {"rate": 3}]
		self.assertEqual(_collect_prices(rows, "rate", lambda r: r["rate"], 2), [1, 2])

	def test_sales_history_shapes(self):
		legacy = get_item_prices(ITEM, self.currency, "_Test Customer", COMPANY)
		self.assertTrue(any(r["invoice"] == self.invoice.name and r["price"] == 123 for r in legacy))
		filters = json.dumps(
			{
				"item_code": ITEM,
				"currency": self.currency,
				"company": COMPANY,
				"customer": "_Test Customer",
				"posting_date": ["Between", [add_days(nowdate(), -1), nowdate()]],
			}
		)
		custom = get_item_prices_custom(filters=filters, start=0, limit=5)
		self.assertTrue(any(r["invoice"] == self.invoice.name and r["rate"] == 123 for r in custom))
		self.assertLessEqual(len(custom), 5)
		self.assertRaises(frappe.ValidationError, get_item_prices_custom, filters="{not json")

	def test_purchase_history_shapes(self):
		legacy = get_item_prices_po(ITEM, self.currency, "_Test Supplier", COMPANY)
		self.assertTrue(any(r["invoice"] == self.purchase.name and r["price"] == 77 for r in legacy))
		custom = get_item_prices_custom_po(
			filters={
				"item_code": ITEM,
				"currency": self.currency,
				"company": COMPANY,
				"customer": "_Test Supplier",
			}
		)
		self.assertTrue(any(r["invoice"] == self.purchase.name and r["rate"] == 77 for r in custom))

	def test_item_info_balances(self):
		rows = get_item_info(ITEM)
		warehouse_rows = [r for r in rows if r["warehouse"] == WAREHOUSE]
		self.assertTrue(warehouse_rows)
		self.assertIn("actual_qty", warehouse_rows[0])
		self.assertEqual(get_item_info("no-such-item"), [])
