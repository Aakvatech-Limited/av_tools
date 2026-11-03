"""Configuration and immutable-price guards for the module's DocTypes."""

import frappe
from frappe import _
from frappe.utils import getdate

from av_tools.selling_pricing_engine.access import (
	LOCATION,
	POLICY,
	RULE,
	SETTINGS,
	check_context,
	check_native_price_writes,
)
from av_tools.selling_pricing_engine.calculation import METHODS, ROUNDING, number, validate_method
from av_tools.selling_pricing_engine.repository import digest, overlaps, uom_factor


def dates(doc):
	if doc.get("valid_upto") and getdate(doc.valid_upto) < getdate(doc.valid_from):
		frappe.throw(_("Valid Upto cannot be earlier than Valid From."))


def configuration(doc):
	try:
		if doc.doctype == SETTINGS or doc.calculation_mode == "Override":
			validate_method(doc.calculation_method, doc.calculation_value)
		if doc.doctype == SETTINGS or doc.rounding_mode == "Override":
			if doc.rounding_method not in ("No Rounding", *ROUNDING):
				raise ValueError("Select a supported rounding method")
			if number(doc.rounding_increment or 0) <= 0:
				raise ValueError("Rounding increment must be greater than zero")
		if doc.doctype == SETTINGS:
			if not 0 <= number(doc.minimum_margin) < 100:
				raise ValueError("Minimum margin must be between 0 and less than 100%")
			if not 1 <= int(doc.rate_precision or 0) <= 9:
				raise ValueError("Rate precision must be between 1 and 9")
			if not 1 <= int(doc.max_revision_items or 0) <= 5000:
				raise ValueError("Maximum revision items must be between 1 and 5,000")
	except ValueError as exc:
		frappe.throw(str(exc))


def settings(doc):
	check_context(doc.company)
	configuration(doc)
	if doc.enabled:
		check_native_price_writes()


def lock_company(company):
	# Configuration changes serialize with publication for the same Company.
	if frappe.db.exists(SETTINGS, company):
		frappe.get_doc(SETTINGS, company, for_update=True)


def policy(doc):
	lock_company(doc.company)
	check_context(doc.company, doc.price_list)
	configuration(doc)
	pl = frappe.get_doc("Price List", doc.price_list)
	if not pl.enabled or not pl.selling:
		frappe.throw(_("Select an enabled selling Price List."))
	if doc.fallback_price_list:
		base = frappe.get_doc("Price List", doc.fallback_price_list)
		check_context(doc.company, base.name)
		if not base.enabled or not base.selling or base.currency != pl.currency:
			frappe.throw(_("Fallback Price List must be enabled, selling and use the target list currency."))
	# One managed standard list belongs to one Company. ERPNext Item Price has no Company field.
	if frappe.db.exists(POLICY, {"price_list": doc.price_list, "company": ["!=", doc.company]}):
		frappe.throw(_("This Price List is already managed for another Company. Use separate Price Lists."))
	seen, current = {doc.price_list}, doc.fallback_price_list
	while current:
		if current in seen:
			frappe.throw(_("Fallback Price Lists cannot form a cycle."))
		seen.add(current)
		parent = frappe.db.get_value(
			POLICY, {"price_list": current}, ["company", "fallback_price_list"], as_dict=True, for_update=True
		)
		if parent and parent.company != doc.company:
			frappe.throw(_("Fallback pricing cannot use a list managed for another Company."))
		current = parent.fallback_price_list if parent else None


def rule(doc):
	lock_company(doc.company)
	check_context(doc.company, doc.price_list, doc.warehouse, doc.item_code)
	dates(doc)
	configuration(doc)
	if (
		doc.calculation_mode == "Override"
		and doc.calculation_method == "Fixed Selling Price"
		and not (doc.item_code and doc.uom)
	):
		frappe.throw(_("Fixed selling prices require an Item and UOM."))
	if doc.item_code and doc.uom:
		uom_factor(frappe.get_doc("Item", doc.item_code), doc.uom)
	if doc.disabled:
		return
	filters = {
		"company": doc.company,
		"price_list": doc.price_list,
		"disabled": 0,
		"name": ["!=", doc.name or ""],
	}
	peers = frappe.get_all(
		RULE, filters=filters, fields=["name", "item_code", "warehouse", "uom", "valid_from", "valid_upto"]
	)
	for peer in peers:
		if all(
			(peer.get(key) or "") == (doc.get(key) or "") for key in ("item_code", "warehouse", "uom")
		) and overlaps(peer, doc.valid_from, doc.valid_upto):
			frappe.throw(_("Pricing rule overlaps equally specific rule {0}.").format(peer.name))


def location(doc):
	if not doc.flags.get("spe_publishing"):
		frappe.throw(_("Location prices are published through a Selling Price Revision."))
	check_context(doc.company, doc.price_list, doc.warehouse, doc.item_code)
	dates(doc)
	if number(doc.rate) <= 0:
		frappe.throw(_("Published rates must be positive."))
	doc.price_key = digest(
		[doc.company, doc.price_list, doc.item_code, doc.warehouse, doc.uom, str(doc.valid_from)]
	)
	peers = frappe.get_all(
		LOCATION,
		filters={
			"company": doc.company,
			"price_list": doc.price_list,
			"item_code": doc.item_code,
			"warehouse": doc.warehouse,
			"uom": doc.uom,
			"enabled": 1,
			"name": ["!=", doc.name or ""],
		},
		fields=["name", "valid_from", "valid_upto"],
	)
	if doc.enabled and any(overlaps(peer, doc.valid_from, doc.valid_upto) for peer in peers):
		frappe.throw(_("Location price validity overlaps an existing published price."))
