import frappe

REPORTS = (
	"Salary Register csf",
	"Salary Register CTC",
	"Salary Register Summary",
	"Salary Register Summary with Components",
	"Employee Salary Register with Monthly Comparison",
	"Salary Register Summary with Monthly Comparison",
)


def execute():
	for report_name in REPORTS:
		if frappe.db.exists("Report", report_name):
			frappe.db.set_value("Report", report_name, "module", "Av Tools")
