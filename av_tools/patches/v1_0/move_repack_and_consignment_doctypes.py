import frappe

DOCTYPES = (
	"Repack Template",
	"Repack Template Detail",
	"Item Barcode Update Tool",
	"Work Order Consignment",
	"Work Order Consignment Detail",
)


def execute():
	for doctype_name in DOCTYPES:
		if frappe.db.exists("DocType", doctype_name):
			frappe.db.set_value("DocType", doctype_name, "module", "Av Tools")
