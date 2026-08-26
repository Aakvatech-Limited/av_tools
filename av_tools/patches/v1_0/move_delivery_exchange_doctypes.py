import frappe


DELIVERY_EXCHANGE_DOCTYPES = (
	"Delivery Exchange Item",
	"Delivery Exchange Item Details",
	"Delivery Exchange Non Stock Item Details",
)


def execute():
	for doctype in DELIVERY_EXCHANGE_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.db.set_value("DocType", doctype, "module", "Av Tools")
