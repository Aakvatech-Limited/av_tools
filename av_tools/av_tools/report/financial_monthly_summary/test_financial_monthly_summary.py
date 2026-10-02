from frappe import _dict
from frappe.tests.utils import FrappeTestCase

from erpnext.accounts.report.general_ledger import general_ledger

from av_tools.av_tools.report.financial_monthly_summary.financial_monthly_summary import (
	_get_general_ledger_filters,
	_get_month_row,
)


class TestFinancialMonthlySummary(FrappeTestCase):
	def test_general_ledger_filters_narrow_to_month_account_and_party(self):
		filters = _dict(
			company="Test Company",
			account="Debtors - TC",
			party_type="Customer",
			party="CUST-0001",
			from_date="2026-01-01",
			to_date="2026-12-31",
			business_unit=["Consulting"],
		)
		period = _dict(from_date="2026-04-01", to_date="2026-04-30")

		resolved = _get_general_ledger_filters(filters, period)

		self.assertEqual(resolved.account, ["Debtors - TC"])
		self.assertEqual(resolved.party, ["CUST-0001"])
		self.assertEqual(resolved.from_date, "2026-04-01")
		self.assertEqual(resolved.to_date, "2026-04-30")
		self.assertEqual(resolved.business_unit, ["Consulting"])

	def test_month_row_uses_standard_general_ledger_totals(self):
		labels = general_ledger.get_translated_labels_for_totals()
		period = _dict(label="Apr 2026", from_date="2026-04-01", to_date="2026-04-30")
		gl_data = [
			_dict(account=labels["opening"], debit=100, credit=0),
			_dict(account=labels["total"], debit=40, credit=10),
			_dict(account=labels["closing"], debit=130, credit=0),
		]

		row = _get_month_row(period, gl_data)

		self.assertEqual(row.opening_debit, 100)
		self.assertEqual(row.debit, 40)
		self.assertEqual(row.credit, 10)
		self.assertEqual(row.closing_debit, 130)
