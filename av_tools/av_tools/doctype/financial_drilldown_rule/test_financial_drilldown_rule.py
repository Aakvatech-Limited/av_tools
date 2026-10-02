import frappe
from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools.doctype.financial_drilldown_rule.financial_drilldown_rule import (
	_get_account_details,
	get_matching_rule,
	resolve_filter_template,
)
from av_tools.patches.v1_0.seed_financial_drilldown_rules import DEFAULT_RULES


class TestFinancialDrilldownRule(FrappeTestCase):
	def test_resolve_filter_template_preserves_types_and_omits_optional_values(self):
		template = {
			"company": "{ctx.company}",
			"account": "{row.account}",
			"cost_center": "{ctx.cost_center?}",
			"accounts": "{row.accounts?}",
		}
		resolved = resolve_filter_template(
			template,
			{"company": "Test Company", "cost_center": []},
			{"account": "Debtors - TC", "accounts": ["Debtors - TC"]},
		)

		self.assertEqual(resolved["company"], "Test Company")
		self.assertEqual(resolved["account"], "Debtors - TC")
		self.assertEqual(resolved["accounts"], ["Debtors - TC"])
		self.assertNotIn("cost_center", resolved)

	def test_coalesce_uses_first_present_value(self):
		template = {
			"to_date": {
				"$coalesce": ["{row.to_date?}", "{row.year_end_date?}", "{ctx.period_end_date?}"]
			}
		}
		resolved = resolve_filter_template(
			template,
			{"period_end_date": "2026-12-31"},
			{"year_end_date": "2026-06-30"},
		)

		self.assertEqual(resolved["to_date"], "2026-06-30")

	def test_inherit_context_keeps_dimensions_and_allows_overrides(self):
		template = {
			"$inherit_context": True,
			"account": "{row.account}",
			"to_date": "{row.to_date}",
		}
		resolved = resolve_filter_template(
			template,
			{
				"company": "Test Company",
				"cost_center": ["Main - TC"],
				"business_unit": ["Consulting"],
				"to_date": "2026-12-31",
			},
			{"account": "Debtors - TC", "to_date": "2026-06-30"},
		)

		self.assertEqual(resolved["business_unit"], ["Consulting"])
		self.assertEqual(resolved["cost_center"], ["Main - TC"])
		self.assertEqual(resolved["account"], "Debtors - TC")
		self.assertEqual(resolved["to_date"], "2026-06-30")

	def test_account_context_is_promoted_for_downstream_rows(self):
		row_context = {}
		report_context = {"account": "Debtors - TC"}

		original_get_cached_value = frappe.get_cached_value
		try:
			frappe.get_cached_value = lambda *args, **kwargs: frappe._dict(
				account_type="Receivable", root_type="Asset"
			)
			_get_account_details(row_context, report_context)
		finally:
			frappe.get_cached_value = original_get_cached_value

		self.assertEqual(row_context["account"], "Debtors - TC")
		self.assertEqual(row_context["account_type"], "Receivable")
		self.assertEqual(row_context["root_type"], "Asset")

	def test_receivable_rule_chain_prefers_source_scoped_next_step(self):
		rules = [frappe._dict(rule) for rule in DEFAULT_RULES]
		original_get_all = frappe.get_all
		original_get_cached_value = frappe.get_cached_value

		def fake_get_all(doctype, *args, **kwargs):
			if doctype == "Financial Drilldown Rule":
				return rules
			return original_get_all(doctype, *args, **kwargs)

		try:
			frappe.get_all = fake_get_all
			frappe.get_cached_value = lambda *args, **kwargs: frappe._dict(
				account_type="Receivable", root_type="Asset"
			)

			account_rule = get_matching_rule(
				{"company": "Test Company"},
				{"account": "Debtors - TC"},
				"Trial Balance",
			)
			self.assertEqual(account_rule.target_report, "Financial Master Summary")

			monthly_rule = get_matching_rule(
				{"company": "Test Company", "account": "Debtors - TC"},
				{"party_type": "Customer", "party": "CUST-0001"},
				"Financial Master Summary",
			)
			self.assertEqual(monthly_rule.target_report, "Financial Monthly Summary")

			ledger_rule = get_matching_rule(
				{
					"company": "Test Company",
					"account": "Debtors - TC",
					"party_type": "Customer",
					"party": "CUST-0001",
				},
				{"from_date": "2026-04-01", "to_date": "2026-04-30"},
				"Financial Monthly Summary",
			)
			self.assertEqual(ledger_rule.target_report, "Financial Drilldown Ledger")
		finally:
			frappe.get_all = original_get_all
			frappe.get_cached_value = original_get_cached_value
