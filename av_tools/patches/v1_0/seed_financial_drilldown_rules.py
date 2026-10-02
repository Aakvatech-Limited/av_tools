import json

import frappe


DEFAULT_RULES = (
	{
		"rule_name": "Receivable Account Summary",
		"account_type": "Receivable",
		"target_report": "Financial Account Summary",
		"priority": 100,
		"base_filter_template": {
			"$inherit_context": True,
			"company": "{ctx.company}",
			"account": {
				"$coalesce": ["{row.account?}", "{row.accounts?}"]
			},
			"from_date": {
				"$coalesce": [
					"{row.from_date?}",
					"{row.year_start_date?}",
					"{ctx.period_start_date?}",
				]
			},
			"to_date": {
				"$coalesce": [
					"{row.to_date?}",
					"{row.year_end_date?}",
					"{ctx.period_end_date?}",
				]
			},
		},
	},
	{
		"rule_name": "Payable Account Summary",
		"account_type": "Payable",
		"target_report": "Financial Account Summary",
		"priority": 100,
		"base_filter_template": {
			"$inherit_context": True,
			"company": "{ctx.company}",
			"account": {
				"$coalesce": ["{row.account?}", "{row.accounts?}"]
			},
			"from_date": {
				"$coalesce": [
					"{row.from_date?}",
					"{row.year_start_date?}",
					"{ctx.period_start_date?}",
				]
			},
			"to_date": {
				"$coalesce": [
					"{row.to_date?}",
					"{row.year_end_date?}",
					"{ctx.period_end_date?}",
				]
			},
		},
	},
	{
		"rule_name": "Receivable Master Summary",
		"source_report": "Financial Account Summary",
		"account_type": "Receivable",
		"target_report": "Financial Master Summary",
		"priority": 200,
		"base_filter_template": {
			"$inherit_context": True,
			"company": "{ctx.company}",
			"account": "{row.account}",
			"from_date": "{ctx.from_date}",
			"to_date": "{ctx.to_date}",
		},
	},
	{
		"rule_name": "Payable Master Summary",
		"source_report": "Financial Account Summary",
		"account_type": "Payable",
		"target_report": "Financial Master Summary",
		"priority": 200,
		"base_filter_template": {
			"$inherit_context": True,
			"company": "{ctx.company}",
			"account": "{row.account}",
			"from_date": "{ctx.from_date}",
			"to_date": "{ctx.to_date}",
		},
	},
	{
		"rule_name": "Receivable Party Monthly Summary",
		"source_report": "Financial Master Summary",
		"account_type": "Receivable",
		"target_report": "Financial Monthly Summary",
		"priority": 300,
		"base_filter_template": {
			"$inherit_context": True,
			"company": "{ctx.company}",
			"account": "{ctx.account}",
			"party_type": "{row.party_type}",
			"party": "{row.party}",
			"from_date": "{ctx.from_date}",
			"to_date": "{ctx.to_date}",
		},
	},
	{
		"rule_name": "Payable Party Monthly Summary",
		"source_report": "Financial Master Summary",
		"account_type": "Payable",
		"target_report": "Financial Monthly Summary",
		"priority": 300,
		"base_filter_template": {
			"$inherit_context": True,
			"company": "{ctx.company}",
			"account": "{ctx.account}",
			"party_type": "{row.party_type}",
			"party": "{row.party}",
			"from_date": "{ctx.from_date}",
			"to_date": "{ctx.to_date}",
		},
	},
	{
		"rule_name": "Monthly Summary General Ledger",
		"source_report": "Financial Monthly Summary",
		"target_report": "Financial Drilldown Ledger",
		"priority": 400,
		"base_filter_template": {
			"$inherit_context": True,
			"company": "{ctx.company}",
			"account": ["{ctx.account}"],
			"party_type": "{ctx.party_type}",
			"party": ["{ctx.party}"],
			"from_date": "{row.from_date}",
			"to_date": "{row.to_date}",
			"categorize_by": "Categorize by Voucher (Consolidated)",
			"include_dimensions": 1,
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
