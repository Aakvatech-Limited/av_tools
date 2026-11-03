"""Atomic, repeatable publication. Called only during a permitted Revision submit."""

import frappe
from frappe import _
from frappe.utils import add_days

from av_tools.selling_pricing_engine import repository as store
from av_tools.selling_pricing_engine.access import LOCATION, RULE


def publish_row(revision, row):
	doctype = LOCATION if row.warehouse else "Item Price"
	if doctype == "Item Price":
		# Revision permissions alone must not bypass standard Item Price permissions.
		frappe.has_permission("Item Price", "write", throw=True)
		frappe.has_permission("Item Price", "create", throw=True)
	prices = store.price_rows(
		revision.company, revision.price_list, row.item_code, row.uom, row.warehouse, lock=True
	)
	overlaps = [price for price in prices if store.overlaps(price, row.valid_from, row.valid_upto)]
	if len(overlaps) > 1:
		frappe.throw(_("Resolve overlapping prices before publishing."))
	previous = overlaps[0] if overlaps else None
	if previous and previous.valid_from and str(previous.valid_from) > str(row.valid_from):
		frappe.throw(_("The publication period overlaps a future price."))
	if previous and str(previous.valid_from) == str(row.valid_from):
		price = frappe.get_doc(doctype, previous.name, for_update=True)
	else:
		if previous:
			old = frappe.get_doc(doctype, previous.name, for_update=True)
			old.valid_upto = add_days(row.valid_from, -1)
			old.flags.spe_publishing = True
			old.save(ignore_permissions=bool(row.warehouse))
		price = frappe.new_doc(doctype)
	price.update(
		{
			"item_code": row.item_code,
			"price_list": revision.price_list,
			"uom": row.uom,
			"currency": row.currency,
			"valid_from": row.valid_from,
			"valid_upto": row.valid_upto,
		}
	)
	if row.warehouse:
		price.update(
			{
				"company": revision.company,
				"warehouse": row.warehouse,
				"rate": row.proposed_rate,
				"enabled": 1,
				"cost_rate": row.cost_rate,
				"cost_available": row.cost_available,
				"supplier": row.supplier,
				"source_invoice": row.source_invoice,
				"pricing_rule": row.pricing_rule,
				"revision": revision.name,
				"price_source": row.price_source,
				"calculated_on": revision.calculated_on,
			}
		)
		price.flags.spe_publishing = True
	else:
		price.price_list_rate = row.proposed_rate
		price.custom_spe_revision = revision.name
		price.custom_spe_company = revision.company
	price.save(ignore_permissions=bool(row.warehouse))
	row.published_doctype, row.published_price = doctype, price.name
	if row.price_source == "Imported Fixed Price":
		row.pricing_rule = protect_imported_price(revision, row)
		if row.warehouse:
			# Update provenance inside the same transaction, without changing the rate.
			price.pricing_rule = row.pricing_rule
			price.save(ignore_permissions=True)
	row.result = "Published"


def protect_imported_price(revision, row):
	filters = {
		"company": revision.company,
		"price_list": revision.price_list,
		"item_code": row.item_code,
		"warehouse": row.warehouse or ["is", "not set"],
		"uom": row.uom,
		"disabled": 0,
	}
	existing = [
		candidate
		for candidate in frappe.get_all(RULE, filters=filters, fields=["name", "valid_from", "valid_upto"])
		if store.overlaps(candidate, row.valid_from, row.valid_upto)
	]
	if len(existing) > 1:
		frappe.throw(_("Multiple fixed-price rules match this import."))
	if existing and str(existing[0].valid_from or "") < str(row.valid_from):
		previous = frappe.get_doc(RULE, existing[0].name, for_update=True)
		previous.valid_upto = add_days(row.valid_from, -1)
		previous.save()
		existing = []
	if existing and str(existing[0].valid_from) != str(row.valid_from):
		frappe.throw(_("Resolve a future rule overlap before importing a replacement fixed price."))
	rule = frappe.get_doc(RULE, existing[0].name) if existing else frappe.new_doc(RULE)
	rule.update(
		{
			"company": revision.company,
			"price_list": revision.price_list,
			"item_code": row.item_code,
			"warehouse": row.warehouse,
			"uom": row.uom,
			"valid_from": row.valid_from,
			"valid_upto": row.valid_upto,
			"calculation_mode": "Override",
			"calculation_method": "Fixed Selling Price",
			"calculation_value": row.proposed_rate,
			"rounding_mode": "Override",
			"rounding_method": "No Rounding",
			"rounding_increment": 1,
			"import_revision": revision.name,
		}
	)
	rule.save()
	return rule.name
