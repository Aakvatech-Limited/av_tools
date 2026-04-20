import frappe
from frappe import _

from erpnext.buying.doctype.purchase_order.purchase_order import (
	close_or_unclose_purchase_orders as original_close_or_unclose_purchase_orders,
	update_status as original_update_purchase_order_status,
)
from erpnext.stock.doctype.material_request.material_request import (
	update_status as original_update_material_request_status,
)
from erpnext.stock.get_item_details import get_item_details as original_get_item_details


SETTINGS_DOCTYPE = "AV Tools Settings"


def _get_setting(fieldname):
	return frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname)


def _is_reopen_allowed(toggle_field, role_field):
	if not _get_setting(toggle_field):
		return True

	configured_role = _get_setting(role_field)
	return bool(configured_role and configured_role in frappe.get_roles())


def _throw_reopen_not_allowed(label, name=None):
	if name:
		frappe.throw(_("You are not allowed to reopen this {0}: <b>{1}</b>").format(label, name))

	frappe.throw(_("<b>You are not allowed to reopen {0}</b>").format(label))


@frappe.whitelist()
def update_purchase_order_status(status, name):
	if status != "Submitted":
		return original_update_purchase_order_status(status, name)

	if not _is_reopen_allowed("allow_reopen_of_po_based_on_role", "role_to_reopen_po"):
		_throw_reopen_not_allowed(_("Purchase Order"), name)

	return original_update_purchase_order_status(status, name)


@frappe.whitelist()
def close_or_unclose_purchase_orders(names, status):
	if status != "Submitted":
		return original_close_or_unclose_purchase_orders(names, status)

	if not _is_reopen_allowed("allow_reopen_of_po_based_on_role", "role_to_reopen_po"):
		_throw_reopen_not_allowed(_("Purchase Orders"))

	return original_close_or_unclose_purchase_orders(names, status)


@frappe.whitelist()
def update_material_request_status(name, status):
	if status != "Submitted":
		return original_update_material_request_status(name, status)

	if not _is_reopen_allowed(
		"allow_reopen_of_material_request_based_on_role",
		"role_to_reopen_material_request",
	):
		_throw_reopen_not_allowed(_("Material Request"), name)

	return original_update_material_request_status(name, status)


@frappe.whitelist()
def get_item_details(args, doc=None, for_validate=False, overwrite_warehouse=True):
	response = original_get_item_details(args, doc, for_validate, overwrite_warehouse)

	if _get_setting("override_sales_invoice_qty"):
		response.pop("qty", None)

	return response
