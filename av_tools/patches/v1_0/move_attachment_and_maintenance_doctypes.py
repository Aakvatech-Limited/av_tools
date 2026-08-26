import frappe

DOCTYPES = (
	"Maintenance Request",
	"Document Attachment",
	"Attachment Type",
	"File Attachment",
)


def execute():
	for doctype in DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.db.set_value("DocType", doctype, "module", "Av Tools")
