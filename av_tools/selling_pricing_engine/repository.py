"""Permission-scoped master data, comparable costs and published price reads."""

import hashlib
import json
from decimal import Decimal

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull
from frappe.utils import cint, getdate

from av_tools.selling_pricing_engine.access import LOCATION, POLICY, RULE, check_context
from av_tools.selling_pricing_engine.calculation import number


def digest(value):
	return hashlib.sha256(
		json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
	).hexdigest()


def policy_for(company, price_list, *, lock=False):
	names = frappe.get_all(
		POLICY, filters={"company": company, "price_list": price_list, "enabled": 1}, pluck="name"
	)
	if len(names) != 1:
		frappe.throw(_("Configure one enabled Selling Price List Policy for this Company and Price List."))
	policy = frappe.get_doc(POLICY, names[0], for_update=lock)
	target = frappe.get_doc("Price List", price_list, for_update=lock)
	if not target.enabled or not target.selling:
		frappe.throw(_("The target Price List must still be enabled for selling."))
	if policy.fallback_price_list:
		check_context(company, policy.fallback_price_list)
		base = frappe.get_doc("Price List", policy.fallback_price_list, for_update=lock)
		if not base.enabled or not base.selling or base.currency != target.currency:
			frappe.throw(_("Fallback Price List must still be enabled, selling and use the target currency."))
		owner = frappe.db.get_value(POLICY, {"price_list": base.name}, "company", for_update=lock)
		if owner and owner != company:
			frappe.throw(_("Fallback Price List is managed for another Company."))
	return policy


def item_for(item_code, effective_date):
	check_context(None, item_code=item_code)
	item = frappe.get_doc("Item", item_code)
	if item.disabled or not item.is_sales_item or item.has_variants or item.is_fixed_asset:
		raise ValueError("Item must be enabled, sellable, non-template and not a fixed asset")
	if item.end_of_life and getdate(item.end_of_life) < getdate(effective_date):
		raise ValueError("Item has reached its end of life")
	return item


def uom_factor(item, uom):
	if uom == item.stock_uom:
		return Decimal(1)
	for row in item.get("uoms") or []:
		if row.uom == uom and number(row.conversion_factor) > 0:
			return number(row.conversion_factor)
	frappe.throw(_("No positive UOM conversion for {0} / {1}.").format(item.name, uom))


def rules_for(
	company, price_list, *, item_code=None, warehouse=None, uom=None, effective_date=None, lock=False
):
	t = frappe.qb.DocType(RULE)
	query = (
		frappe.qb.from_(t)
		.select(t.star)
		.where((t.company == company) & (t.price_list == price_list) & (t.disabled == 0))
	)
	for field, value in (("item_code", item_code), ("warehouse", warehouse), ("uom", uom)):
		query = query.where(IfNull(t[field], "").isin(["", value] if value else [""]))
	if effective_date:
		query = query.where(
			(t.valid_from <= effective_date) & ((t.valid_upto.isnull()) | (t.valid_upto >= effective_date))
		)
	query = query.orderby(t.name)
	if lock:
		query = query.for_update()
	return query.run(as_dict=True)


def purchase_cost(company, item, uom, currency, effective_date, *, lock=False):
	"""Latest permitted submitted non-return invoice, never Item.last_purchase_rate.

	Native get_list enforces Purchase Invoice role, company and User Permissions.
	Cost is base_net_amount / stock_qty, then stock-UOM → selling-UOM and FX.
	"""
	frappe.has_permission("Purchase Invoice", "read", throw=True)
	filters = [
		["Purchase Invoice", "company", "=", company],
		["Purchase Invoice", "docstatus", "=", 1],
		["Purchase Invoice", "is_return", "=", 0],
		["Purchase Invoice", "posting_date", "<=", effective_date],
		["Purchase Invoice Item", "item_code", "=", item.name],
		["Purchase Invoice Item", "stock_qty", ">", 0],
		["Purchase Invoice Item", "base_net_amount", ">", 0],
	]
	names = frappe.get_list(
		"Purchase Invoice",
		filters=filters,
		fields=["name", "posting_date", "creation"],
		distinct=True,
		order_by="posting_date desc, creation desc, name desc",
		limit_page_length=1,
	)
	if not names:
		return {
			"cost_rate": None,
			"cost_reason": "No permitted submitted Purchase Invoice with a positive comparable cost",
		}
	invoice = frappe.get_doc("Purchase Invoice", names[0].name, for_update=lock)
	invoice.check_permission("read")
	if invoice.docstatus != 1 or invoice.is_return or invoice.company != company:
		raise ValueError("Purchase Invoice changed during calculation")
	lines = [
		row
		for row in invoice.items
		if row.item_code == item.name
		and number(row.stock_qty or 0) > 0
		and number(row.base_net_amount or 0) > 0
	]
	if not lines:
		raise ValueError("Purchase Invoice no longer contains a usable cost")
	line = max(lines, key=lambda row: row.idx)
	base_currency = frappe.get_cached_value("Company", company, "default_currency")
	fx, fx_reference = exchange_rate(base_currency, currency, effective_date, lock=lock)
	cost = number(line.base_net_amount) / number(line.stock_qty) * uom_factor(item, uom) * fx
	return {
		"cost_rate": float(cost),
		"cost_source": "Latest Submitted Purchase Invoice",
		"source_invoice": invoice.name,
		"source_invoice_item": line.name,
		"supplier": invoice.supplier,
		"cost_date": str(invoice.posting_date),
		"cost_modified": str(invoice.modified),
		"source_stock_qty": line.stock_qty,
		"source_base_net_amount": line.base_net_amount,
		"exchange_rate": float(fx),
		"exchange_reference": fx_reference,
	}


def exchange_rate(from_currency, to_currency, date, *, lock=False):
	if from_currency == to_currency:
		return Decimal(1), "Same currency"
	# Deliberately require a stored, dated rate; never call an external FX service
	# during publication or assume 1 when no conversion is available.
	for source, target, inverse in ((from_currency, to_currency, False), (to_currency, from_currency, True)):
		t = frappe.qb.DocType("Currency Exchange")
		query = (
			frappe.qb.from_(t)
			.select(t.name, t.exchange_rate, t.modified)
			.where(
				(t.from_currency == source)
				& (t.to_currency == target)
				& (t.date <= date)
				& (t.exchange_rate > 0)
			)
			.orderby(t.date, order=frappe.qb.desc)
			.orderby(t.name, order=frappe.qb.desc)
			.limit(1)
		)
		if lock:
			query = query.for_update()
		rows = query.run(as_dict=True)
		if rows:
			rate = number(rows[0].exchange_rate)
			return (1 / rate if inverse else rate), f"{rows[0].name} / {rows[0].modified}"
	raise ValueError(f"No stored Currency Exchange rate for {from_currency} to {to_currency} on {date}")


def price_rows(company, price_list, item_code, uom, warehouse=None, *, lock=False):
	doctype = LOCATION if warehouse else "Item Price"
	t = frappe.qb.DocType(doctype)
	query = frappe.qb.from_(t).select(t.star).where((t.item_code == item_code) & (t.price_list == price_list))
	if warehouse:
		query = query.where(
			(t.company == company) & (t.warehouse == warehouse) & (t.enabled == 1) & (t.uom == uom)
		)
	else:
		stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
		query = query.where(IfNull(t.uom, "").isin([uom, ""] if uom == stock_uom else [uom]))
		for field in ("customer", "supplier", "batch_no"):
			query = query.where(IfNull(t[field], "") == "")
		query = query.where(IfNull(t.packing_unit, 0) == 0)
	if lock:
		query = query.for_update()
	return query.run(as_dict=True)


def valid_price(rows, effective_date):
	matches = [
		row
		for row in rows
		if (not row.valid_from or getdate(row.valid_from) <= getdate(effective_date))
		and (not row.valid_upto or getdate(row.valid_upto) >= getdate(effective_date))
	]
	if len(matches) > 1:
		raise ValueError(
			"Overlapping published prices must be resolved before pricing: "
			+ ", ".join(row.name for row in matches)
		)
	return matches[0] if matches else None


def standard_price(company, price_list, item, uom, effective_date, *, lock=False):
	"""Resolve an exact standard price, then a comparable stock-UOM price.

	Never use a price from an unrelated UOM. Stock conversions require the Item's
	actual conversion factor; Price Not UOM Dependent keeps the source rate.
	"""
	price = valid_price(price_rows(company, price_list, item.name, uom, lock=lock), effective_date)

	def check_currency(candidate):
		if candidate and candidate.currency != frappe.get_cached_value("Price List", price_list, "currency"):
			raise ValueError(
				"Published Item Price currency differs from its Price List; resolve the currency before pricing"
			)

	check_currency(price)
	if price or uom == item.stock_uom:
		return price
	price = valid_price(price_rows(company, price_list, item.name, item.stock_uom, lock=lock), effective_date)
	if not price:
		return None
	check_currency(price)
	factor = uom_factor(item, uom)
	if cint(frappe.get_cached_value("Price List", price_list, "price_not_uom_dependent")):
		factor = number(1)
	return frappe._dict(
		{
			**price,
			"price_list_rate": float(number(price.price_list_rate) * factor),
			"source_rate": price.price_list_rate,
			"source_uom": price.uom or item.stock_uom,
			"normalization_factor": float(factor),
			"uom": uom,
		}
	)


def price_snapshot(row):
	if not row:
		return None
	return {
		key: row.get(key)
		for key in (
			"name",
			"modified",
			"price_list_rate",
			"rate",
			"valid_from",
			"valid_upto",
			"uom",
			"currency",
			"source_rate",
			"source_uom",
			"normalization_factor",
		)
	}


def overlaps(row, start, end):
	return getdate(row.get("valid_from") or "1900-01-01") <= getdate(end or "9999-12-31") and getdate(
		row.get("valid_upto") or "9999-12-31"
	) >= getdate(start)
