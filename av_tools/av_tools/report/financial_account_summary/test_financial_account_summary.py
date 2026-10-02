from frappe import _dict
from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools.report.financial_account_summary.financial_account_summary import (
	_merge_segment_rows,
)


class TestFinancialAccountSummary(FrappeTestCase):
	def test_merge_segment_rows_keeps_first_opening_and_last_closing(self):
		merged = {}
		accounts = {"Debtors - TC"}

		_merge_segment_rows(
			merged,
			[
				_dict(
					account="Debtors - TC",
					opening_debit=100,
					opening_credit=0,
					debit=50,
					credit=10,
					closing_debit=140,
					closing_credit=0,
					has_value=True,
				)
			],
			accounts,
		)
		_merge_segment_rows(
			merged,
			[
				_dict(
					account="Debtors - TC",
					opening_debit=140,
					opening_credit=0,
					debit=25,
					credit=5,
					closing_debit=160,
					closing_credit=0,
					has_value=True,
				)
			],
			accounts,
		)

		row = merged["Debtors - TC"]
		self.assertEqual(row.opening_debit, 100)
		self.assertEqual(row.debit, 75)
		self.assertEqual(row.credit, 15)
		self.assertEqual(row.closing_debit, 160)
