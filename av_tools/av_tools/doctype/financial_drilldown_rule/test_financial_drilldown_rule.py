from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools.doctype.financial_drilldown_rule.financial_drilldown_rule import (
	resolve_filter_template,
)


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
