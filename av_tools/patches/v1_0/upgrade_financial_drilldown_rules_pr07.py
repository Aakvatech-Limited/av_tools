import frappe


RULE_TARGETS = {
	"Receivable Account Summary": ("Financial Account Summary", "Financial Master Summary"),
	"Payable Account Summary": ("Financial Account Summary", "Financial Master Summary"),
}


def execute():
	if not frappe.db.exists("DocType", "Financial Drilldown Rule"):
		return

	for rule_name, (old_target, new_target) in RULE_TARGETS.items():
		if not frappe.db.exists("Financial Drilldown Rule", rule_name):
			continue

		doc = frappe.get_doc("Financial Drilldown Rule", rule_name)
		if doc.target_report != old_target:
			continue

		doc.target_report = new_target
		doc.save(ignore_permissions=True)
