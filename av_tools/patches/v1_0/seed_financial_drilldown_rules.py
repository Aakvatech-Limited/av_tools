import json

import frappe


DEFAULT_RULES = (
	{
		"rule_name": "Receivable Account Summary",
		"account_type": "Receivable",
		"target_report": "Accounts Receivable Summary",
		"priority": 100,
		"base_filter_template": {
			"company": "{ctx.company}",
			"report_date": {
				"$coalesce": [
					"{row.to_date?}",
					"{row.year_end_date?}",
					"{ctx.period_end_date?}",
				]
			},
			"ageing_based_on": "Posting Date",
			"finance_book": "{ctx.finance_book?}",
			"cost_center": "{ctx.cost_center?}",
			"project": "{ctx.project?}",
			"drilldown_account": {
				"$coalesce": ["{row.account?}", "{row.accounts?}"]
			},
		},
	},
	{
		"rule_name": "Payable Account Summary",
		"account_type": "Payable",
		"target_report": "Accounts Payable Summary",
		"priority": 100,
		"base_filter_template": {
			"company": "{ctx.company}",
			"report_date": {
				"$coalesce": [
					"{row.to_date?}",
					"{row.year_end_date?}",
					"{ctx.period_end_date?}",
				]
			},
			"ageing_based_on": "Posting Date",
			"finance_book": "{ctx.finance_book?}",
			"cost_center": "{ctx.cost_center?}",
			"project": "{ctx.project?}",
			"drilldown_account": {
				"$coalesce": ["{row.account?}", "{row.accounts?}"]
			},
		},
	},
)


def execute():
	if not frappe.db.exists("DocType", "Financial Drilldown Rule"):
		return

	for values in DEFAULT_RULES:
		if frappe.db.exists("Financial Drilldown Rule", values["rule_name"]):
			continue
		if not frappe.db.exists("Report", values["target_report"]):
			continue

		doc = frappe.new_doc("Financial Drilldown Rule")
		doc.update(values)
		doc.base_filter_template = json.dumps(values["base_filter_template"], indent=2)
		doc.insert(ignore_permissions=True)
