import frappe


REPORT_NAMES = (
	"Schema Details",
	"Table Indexes",
	"SHOW PROCESSLIST",
	"Version Table Statistics",
	"Transaction Statistics",
	"Master Data Statistics",
)


def execute():
	for report_name in REPORT_NAMES:
		if frappe.db.exists("Report", report_name):
			frappe.db.set_value("Report", report_name, "module", "Av Tools", update_modified=False)
