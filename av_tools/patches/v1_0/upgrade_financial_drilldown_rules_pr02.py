import json

import frappe

from av_tools.patches.v1_0.seed_financial_drilldown_rules import DEFAULT_RULES


LEGACY_TARGETS = {
	"Receivable Account Summary": "Accounts Receivable Summary",
	"Payable Account Summary": "Accounts Payable Summary",
}


def execute():
	if not frappe.db.exists("DocType", "Financial Drilldown Rule"):
		return

	for values in DEFAULT_RULES:
		name = values["rule_name"]
		if not frappe.db.exists("Report", values["target_report"]):
			continue

		if not frappe.db.exists("Financial Drilldown Rule", name):
			doc = frappe.new_doc("Financial Drilldown Rule")
			doc.update(values)
			doc.base_filter_template = json.dumps(values["base_filter_template"], indent=2)
			doc.insert(ignore_permissions=True)
			continue

		legacy_target = LEGACY_TARGETS.get(name)
		if not legacy_target:
			continue

		doc = frappe.get_doc("Financial Drilldown Rule", name)
		if doc.target_report != legacy_target:
			continue

		doc.target_report = values["target_report"]
		doc.priority = values["priority"]
		doc.source_report = values.get("source_report")
		doc.base_filter_template = json.dumps(values["base_filter_template"], indent=2)
		doc.save(ignore_permissions=True)
