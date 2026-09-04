import frappe

from av_tools.utils.legacy_settings import adopt_legacy_value

CHECK_FIELDS = (
	"allow_reopen_of_po_based_on_role",
	"allow_reopen_of_material_request_based_on_role",
	"override_sales_invoice_qty",
	"is_manufacture",
)
LINK_FIELDS = (
	"role_to_reopen_po",
	"role_to_reopen_material_request",
)


def execute():
	"""Carry the generic ERP behaviour flags over from CSF TZ Settings."""
	for fieldname in CHECK_FIELDS:
		adopt_legacy_value(fieldname, default=0, as_int=True)

	for fieldname in LINK_FIELDS:
		adopt_legacy_value(fieldname)

	frappe.db.commit()
