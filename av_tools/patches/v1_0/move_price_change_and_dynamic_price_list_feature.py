import frappe
from frappe.utils import cint


DOCTYPES = (
	"Price Change Request",
	"Price Change Request Detail",
	"Dynamic Price List Assignment",
)


def execute():
	_move_doctypes()
	_move_report()
	_migrate_setting()


def _move_doctypes():
	for doctype in DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.db.set_value("DocType", doctype, "module", "Av Tools")


def _move_report():
	if frappe.db.exists("Report", "Price Change History"):
		frappe.db.set_value("Report", "Price Change History", "module", "Av Tools")


def _migrate_setting():
	legacy_value = None
	if frappe.db.exists("DocType", "CSF TZ Settings") and frappe.get_meta(
		"CSF TZ Settings"
	).has_field("target_warehouse_based_price_list"):
		legacy_value = frappe.db.get_single_value(
			"CSF TZ Settings", "target_warehouse_based_price_list"
		)

	current_value = frappe.db.get_single_value(
		"AV Tools Settings", "target_warehouse_based_price_list"
	)
	if current_value is None:
		frappe.db.set_single_value(
			"AV Tools Settings",
			"target_warehouse_based_price_list",
			cint(legacy_value) if legacy_value is not None else 0,
		)
	elif legacy_value is not None:
		frappe.db.set_single_value(
			"AV Tools Settings", "target_warehouse_based_price_list", cint(legacy_value)
		)

	if legacy_value is not None:
		frappe.db.delete(
			"Singles",
			{
				"doctype": "CSF TZ Settings",
				"field": "target_warehouse_based_price_list",
			},
		)
