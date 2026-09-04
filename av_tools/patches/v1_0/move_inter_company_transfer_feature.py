import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from av_tools.utils.legacy_settings import adopt_legacy_value

INTER_COMPANY_DOCTYPES = (
	"Inter Company Material Request",
	"Inter Company Material Request Details",
	"Inter Company Stock Transfer",
	"Inter Company Stock Transfer Details",
)


def execute():
	_create_custom_fields()
	_migrate_setting_value()
	_move_doctype_modules()


def _create_custom_fields():
	_delete_legacy_custom_fields()

	custom_fields = {}

	if not frappe.db.exists(
		"Custom Field", {"dt": "Stock Entry", "fieldname": "transfer_goods_between_company"}
	):
		custom_fields["Stock Entry"] = [
			{
				"fieldname": "av_tools_inter_company_section",
				"fieldtype": "Section Break",
				"insert_after": "remarks",
				"label": "Inter Company Transfer",
			},
			{
				"fieldname": "transfer_goods_between_company",
				"fieldtype": "Link",
				"insert_after": "av_tools_inter_company_section",
				"label": "Inter Company Stock Transfer",
				"options": "Inter Company Stock Transfer",
			},
		]

	create_custom_fields(custom_fields, update=True)


def _delete_legacy_custom_fields():
	if frappe.db.exists("Custom Field", "Stock Entry-csf_tz_specifics"):
		frappe.delete_doc("Custom Field", "Stock Entry-csf_tz_specifics")
	if frappe.db.exists("Custom Field", "Stock Settings-av_tools_inter_company_section"):
		frappe.delete_doc("Custom Field", "Stock Settings-av_tools_inter_company_section")
	if frappe.db.exists("Custom Field", "Stock Settings-allow_inter_company_stock_transfer"):
		frappe.delete_doc("Custom Field", "Stock Settings-allow_inter_company_stock_transfer")


def _migrate_setting_value():
	adopt_legacy_value("allow_inter_company_stock_transfer", default=0, as_int=True)
	frappe.db.delete(
		"Singles",
		{"doctype": "Stock Settings", "field": "allow_inter_company_stock_transfer"},
	)


def _move_doctype_modules():
	for doctype in INTER_COMPANY_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.db.set_value("DocType", doctype, "module", "Av Tools")
