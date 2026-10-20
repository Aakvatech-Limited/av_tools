from unittest import TestCase
from unittest.mock import patch

from av_tools.api import item_lookups


class TestGetInvoicePrices(TestCase):
	def run_query(self, max_records):
		database = item_lookups.frappe.db
		with patch.object(database, "sql", wraps=database.sql) as sql_spy:
			item_lookups._get_invoice_prices("Sales", "ITEM-001", "TZS", "Test Company", max_records)

		return next(
			str(call.args[0]) for call in sql_spy.call_args_list if "`tabSales Invoice`" in str(call.args[0])
		)

	def test_limit_is_applied_in_the_query(self):
		self.assertTrue(self.run_query(2).endswith("LIMIT 2"))

	def test_rows_without_rate_are_filtered_in_the_query(self):
		self.assertIn("IFNULL(`tabSales Invoice Item`.`rate`,0)<>0", self.run_query(20))

	def test_latest_invoices_come_first_in_a_stable_order(self):
		self.assertIn(
			"ORDER BY `tabSales Invoice`.`posting_date` DESC,`tabSales Invoice`.`name` DESC",
			self.run_query(20),
		)
