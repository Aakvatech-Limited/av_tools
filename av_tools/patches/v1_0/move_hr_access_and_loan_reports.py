import frappe


REPORTS = (
	"Employee Checkin & Checkout Report",
	"Employee Salary Register with Monthly Comparison",
	"Loan Outstanding",
	"Loan Repayment Details",
	"Parent Child Relationship",
	"Payroll for Mobile Payment",
	"Role Permission Listing",
	"User Role Listing",
	"Piecework Net Pay",
	"Customer Loan Assistance report",
)


def execute():
	for report_name in REPORTS:
		if frappe.db.exists("Report", report_name):
			frappe.db.set_value("Report", report_name, "module", "Av Tools")
