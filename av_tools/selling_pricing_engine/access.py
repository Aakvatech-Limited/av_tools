"""Explicit permission checks shared by UI, reports and the publication service."""

import frappe
from frappe import _

SETTINGS = "Selling Price Settings"
POLICY = "Selling Price List Policy"
RULE = "Selling Price Rule"
REVISION = "Selling Price Revision"
LOCATION = "Location Selling Price"


def check_link(doctype, name):
	if name:
		frappe.has_permission(doctype, "select", doc=name, throw=True)


def settings(company, *, lock=False, require_enabled=True):
	if not company or not frappe.db.exists(SETTINGS, company):
		if require_enabled:
			frappe.throw(_("Configure Selling Price Settings for this Company first."))
		return None
	doc = frappe.get_doc(SETTINGS, company, for_update=lock)
	if not doc.enabled:
		if require_enabled:
			frappe.throw(_("Selling Pricing Engine is disabled for this Company."))
		return None
	check_link("Company", company)
	return doc


def check_context(company, price_list=None, warehouse=None, item_code=None):
	for doctype, name in (
		("Company", company),
		("Price List", price_list),
		("Warehouse", warehouse),
		("Item", item_code),
	):
		check_link(doctype, name)
	if warehouse:
		wh = frappe.get_doc("Warehouse", warehouse)
		if wh.company != company or wh.is_group or wh.disabled:
			frappe.throw(_("Select an enabled leaf Warehouse belonging to the pricing Company."))


def manager(company):
	frappe.has_permission(REVISION, "read", throw=True)
	check_context(company)


def check_native_price_writes():
	stock = frappe.get_cached_doc("Stock Settings")
	if stock.get("auto_insert_price_list_rate_if_missing"):
		frappe.throw(
			_(
				"Disable 'Auto insert Price List rate if missing' in Stock Settings before enabling this engine. Native transaction price writes bypass revision review."
			)
		)
