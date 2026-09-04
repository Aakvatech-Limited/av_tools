import frappe

from av_tools.utils.legacy_settings import adopt_legacy_value

DOCTYPES = (
	"Price Change Request",
	"Price Change Request Detail",
	"Dynamic Price List Assignment",
)


def execute():
	_move_doctypes()
	_move_report()
	adopt_legacy_value("target_warehouse_based_price_list", default=0, as_int=True)


def _move_doctypes():
	for doctype in DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.db.set_value("DocType", doctype, "module", "Av Tools")


def _move_report():
	if frappe.db.exists("Report", "Price Change History"):
		frappe.db.set_value("Report", "Price Change History", "module", "Av Tools")
