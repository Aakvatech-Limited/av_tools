import json

import frappe

from av_tools.patches.v1_0.seed_financial_drilldown_rules import DEFAULT_RULES


RULE_NAME = "Monthly Summary General Ledger"
LEGACY_TARGET = "General Ledger"


def execute():
	if not frappe.db.exists("DocType", "Financial Drilldown Rule"):
		return

	values = next((rule for rule in DEFAULT_RULES if rule["rule_name"] == RULE_NAME), None)
	if not values or not frappe.db.exists("Report", values["target_report"]):
		return

	if not frappe.db.exists("Financial Drilldown Rule", RULE_NAME):
		doc = frappe.new_doc("Financial Drilldown Rule")
		doc.update(values)
		doc.base_filter_template = json.dumps(values["base_filter_template"], indent=2)
		doc.insert(ignore_permissions=True)
		return

	doc = frappe.get_doc("Financial Drilldown Rule", RULE_NAME)
	if doc.target_report != LEGACY_TARGET:
		return

	doc.target_report = values["target_report"]
	doc.priority = values["priority"]
	doc.source_report = values.get("source_report")
	doc.base_filter_template = json.dumps(values["base_filter_template"], indent=2)
	doc.save(ignore_permissions=True)
