"""Switch the inspected feature to app code, retaining allocation rows and script bodies."""

import frappe

from av_tools.patches.v1_0.prepare_asset_reconciliation import DOCTYPES

CLIENT_SCRIPTS = (
	"Asset Capitalization Reconciliation Form",
	"Asset Accounting Audit Button",
	"Asset Capitalization Reconciliation Links",
	"Purchase Invoice Capitalization Reconciliation Links",
	"Journal Entry Capitalization Reconciliation Links",
)
SERVER_SCRIPTS = ("Asset Accounting Audit API", "Asset Capitalization Reconciliation Links API")
REPORT = "Fixed Asset Financial Reconciliation"


def execute():
	for name in DOCTYPES:
		frappe.reload_doc("av_tools", "doctype", frappe.scrub(name), force=True)
	# Direct child updates only add derived connection references. Existing row IDs,
	# amounts, parent links, status and audit history are untouched. Do not save parents:
	# legacy Approved allocations may not satisfy today's validation rules.
	for row in frappe.get_all(
		"Asset Reconciliation Source",
		filters={"parenttype": "Asset Capitalization Reconciliation", "parentfield": "sources"},
		fields=["name", "source_voucher_type", "source_voucher"],
	):
		frappe.db.set_value(
			"Asset Reconciliation Source",
			row.name,
			{
				"reconciliation_purchase_invoice": row.source_voucher
				if row.source_voucher_type == "Purchase Invoice"
				else None,
				"reconciliation_journal_entry": row.source_voucher
				if row.source_voucher_type == "Journal Entry"
				else None,
			},
			update_modified=False,
		)
	# Force conversion even if a site's custom report has a newer timestamp.
	# Existing report role overrides were retained as Custom Role before sync.
	frappe.reload_doc("av_tools", "report", frappe.scrub(REPORT), force=True)
	frappe.db.set_value("Report", REPORT, {"module": "Av Tools", "is_standard": "Yes"}, update_modified=False)
	for doctype, names, field, value in (
		("Client Script", CLIENT_SCRIPTS, "enabled", 0),
		("Server Script", SERVER_SCRIPTS, "disabled", 1),
	):
		for name in names:
			if frappe.db.exists(doctype, name):
				frappe.db.set_value(doctype, name, field, value, update_modified=False)
	frappe.clear_cache()
