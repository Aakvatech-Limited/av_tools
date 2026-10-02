import json

import frappe

from av_tools.patches.v1_0.seed_financial_drilldown_rules import DEFAULT_RULES


RULE_NAME = "Monthly Summary General Ledger"
OLD_TEMPLATE = {
	"$inherit_context": True,
	"company": "{ctx.company}",
	"account": ["{ctx.account}"],
	"party_type": "{ctx.party_type}",
	"party": ["{ctx.party}"],
	"from_date": "{row.from_date}",
	"to_date": "{row.to_date}",
	"categorize_by": "Categorize by Voucher (Consolidated)",
	"include_dimensions": 1,
}


def execute():
	if not frappe.db.exists("DocType", "Financial Drilldown Rule"):
		return
	if not frappe.db.exists("Financial Drilldown Rule", RULE_NAME):
		return

	values = next((rule for rule in DEFAULT_RULES if rule["rule_name"] == RULE_NAME), None)
	if not values:
		return

	doc = frappe.get_doc("Financial Drilldown Rule", RULE_NAME)
	try:
		current_template = frappe.parse_json(doc.base_filter_template or "{}")
	except Exception:
		return

	if current_template != OLD_TEMPLATE:
		return

	doc.base_filter_template = json.dumps(values["base_filter_template"], indent=2)
	doc.save(ignore_permissions=True)
