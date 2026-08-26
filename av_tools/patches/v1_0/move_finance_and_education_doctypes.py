import frappe

DOCTYPES = (
	"Employee Salary Component Limit",
	"Bank Statement Summary",
	"Open Invoice Exchange Rate Revaluation",
)


def execute():
	for doctype_name in DOCTYPES:
		if frappe.db.exists("DocType", doctype_name):
			frappe.db.set_value("DocType", doctype_name, "module", "Av Tools")
