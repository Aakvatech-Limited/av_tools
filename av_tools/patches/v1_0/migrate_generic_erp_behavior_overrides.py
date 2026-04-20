import frappe


SETTINGS_DOCTYPE = "AV Tools Settings"
SOURCE_SETTINGS_DOCTYPE = "CSF TZ Settings"
SETTINGS_FIELDS = (
	"allow_reopen_of_po_based_on_role",
	"role_to_reopen_po",
	"allow_reopen_of_material_request_based_on_role",
	"role_to_reopen_material_request",
	"override_sales_invoice_qty",
	"allow_delete_in_sql_command",
	"is_manufacture",
)


def source_settings_doctype_exists():
	return bool(frappe.db.exists("DocType", SOURCE_SETTINGS_DOCTYPE))


def get_source_values():
	return {
		fieldname: frappe.db.get_single_value(SOURCE_SETTINGS_DOCTYPE, fieldname)
		for fieldname in SETTINGS_FIELDS
	}


def execute():
	if not source_settings_doctype_exists():
		return

	for fieldname, value in get_source_values().items():
		frappe.db.set_single_value(SETTINGS_DOCTYPE, fieldname, value)
