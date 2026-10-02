from frappe import _dict
from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools.report.financial_drilldown_ledger.financial_drilldown_ledger import (
	_get_general_ledger_filters,
)


class TestFinancialDrilldownLedger(FrappeTestCase):
	def test_general_ledger_filters_preserve_context_and_normalize_lists(self):
		filters = _dict(
			company="Test Company",
			account="Debtors - TC",
			party_type="Customer",
			party="CUST-0001",
			from_date="2026-04-01",
			to_date="2026-04-30",
			business_unit=["Consulting"],
		)

		resolved = _get_general_ledger_filters(filters)

		self.assertEqual(resolved.account, ["Debtors - TC"])
		self.assertEqual(resolved.party, ["CUST-0001"])
		self.assertEqual(resolved.business_unit, ["Consulting"])
		self.assertEqual(resolved.categorize_by, "Categorize by Voucher (Consolidated)")
		self.assertEqual(resolved.include_dimensions, 1)
