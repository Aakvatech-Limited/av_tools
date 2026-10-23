import json

import frappe
from erpnext.stock.doctype.material_request.material_request import (
	make_supplier_quotation as erpnext_make_supplier_quotation,
)

MAKE_SQ_FROM_MR = "erpnext.stock.doctype.material_request.material_request.make_supplier_quotation"

# Pricing inputs on Supplier Quotation Item that would otherwise come from the
# Material Request (same-name field copy) or the Buying Price List / Pricing Rules.
# base_* / net_* values are derived from these by calculate_taxes_and_totals.
SQ_ITEM_PRICING_FIELDS = (
	"price_list_rate",
	"base_price_list_rate",
	"discount_percentage",
	"discount_amount",
	"margin_rate_or_amount",
	"rate_with_margin",
	"rate",
	"amount",
)


@frappe.whitelist()
def make_supplier_quotation(source_name, target_doc=None):
	"""Wraps the Material Request -> Supplier Quotation mapper; optionally leaves the mapped rows without rates.

	Controlled by AV Tools Settings > "Don't Fetch Rates in Supplier Quotation from
	Material Request". Covers both the Material Request "Create" button and
	Supplier Quotation "Get Items From > Material Request", since map_docs also
	honours override_whitelisted_methods.
	"""
	existing_rows = _get_existing_row_count(target_doc)
	doc = _get_previous_mapper()(source_name, target_doc)

	if not skip_mr_rates():
		return doc

	# Only touch rows added from this Material Request, never rows already on the target.
	for item in doc.items[existing_rows:]:
		if item.material_request != source_name:
			continue

		for fieldname in SQ_ITEM_PRICING_FIELDS:
			if item.meta.has_field(fieldname):
				item.set(fieldname, 0)

		item.margin_type = ""
		item.pricing_rules = ""

	doc.run_method("calculate_taxes_and_totals")

	# ERPNext sets this to False for MR -> SQ so the form re-applies the price list
	# on load; keep Frappe's default (True) so the blank rates are not refilled.
	doc.set_onload("load_after_mapping", True)
	# Tells supplier_quotation.js to keep the price list off these rows on supplier change.
	doc.set_onload("av_skip_mr_rates", True)

	return doc


def set_skip_mr_rates_onload(doc, method=None):
	"""Supplier Quotation onload: same flag for saved quotations reopened in the form."""
	if skip_mr_rates():
		doc.set_onload("av_skip_mr_rates", True)


def skip_mr_rates():
	return frappe.db.get_single_value("AV Tools Settings", "do_not_fetch_rates_in_sq_from_mr")


def _get_previous_mapper():
	# Another app installed before av_tools may override the same method (e.g. sfl);
	# only the last override is called, so chain to it instead of bypassing it.
	overrides = frappe.get_hooks("override_whitelisted_methods").get(MAKE_SQ_FROM_MR, [])
	this = f"{__name__}.make_supplier_quotation"
	earlier = overrides[: overrides.index(this)] if this in overrides else []
	return frappe.get_attr(earlier[-1]) if earlier else erpnext_make_supplier_quotation


def _get_existing_row_count(target_doc):
	if not target_doc:
		return 0

	if isinstance(target_doc, str):
		target_doc = json.loads(target_doc)

	return len(target_doc.get("items") or [])
