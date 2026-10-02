import frappe


REPORTS = (
	"financial_account_summary",
	"financial_master_summary",
	"financial_monthly_summary",
	"financial_drilldown_ledger",
)


def execute():
	for report in REPORTS:
		frappe.reload_doc("av_tools", "report", report, force=True)

	missing = [
		report.replace("_", " ").title()
		for report in REPORTS
		if not frappe.db.exists("Report", report.replace("_", " ").title())
	]
	if missing:
		frappe.throw(
			"Failed to create Financial Drill-down Reports: {0}".format(", ".join(missing))
		)
