"""Server-owned location price retrieval while preserving ERPNext agreements.

Precedence: mapped locked source / customer-specific Item Price / ERPNext
Pricing Rule / authorized explicit manual rate, then warehouse price, then
ERPNext's ordinary Item Price lookup. No cost is exposed by sales endpoints.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from av_tools.selling_pricing_engine import repository
from av_tools.selling_pricing_engine.access import POLICY, check_context, check_native_price_writes, settings
from av_tools.selling_pricing_engine.calculation import number

SALES_DOCTYPES = ("Quotation", "Sales Order", "Sales Invoice")
PRICE_FIELDS = (
	"price_list_rate",
	"rate",
	"custom_spe_price_source",
	"custom_spe_resolved_price_list",
	"custom_spe_resolution",
)


def supported(ctx):
	return ctx.get("doctype") in SALES_DOCTYPES and not any(
		ctx.get(key) for key in ("is_return", "is_pos", "is_internal_customer")
	)


def enabled_context(ctx):
	if not supported(ctx) or not ctx.get("company"):
		return None
	config = settings(ctx["company"], require_enabled=False)
	if config:
		check_native_price_writes()
	return config


def _has_rules(value):
	return bool(frappe.parse_json(value) if isinstance(value, str) else value)


def _preserve(ctx, native, doc, config):
	from erpnext.stock.get_item_details import get_rate_locked_source_row

	if ctx.get("is_free_item") or ctx.get("against_blanket_order") or ctx.get("batch_no"):
		return True
	if get_rate_locked_source_row(ctx, doc):
		return True
	if _has_rules(native.get("pricing_rules")) or native.get("has_pricing_rule"):
		return True
	# Preserve applicable native quantity/packing prices as commercial agreements.
	packing_prices = frappe.get_all(
		"Item Price",
		filters={"price_list": ctx.price_list, "item_code": ctx.item_code, "packing_unit": [">", 0]},
		fields=["packing_unit", "uom", "customer", "supplier", "batch_no", "valid_from", "valid_upto"],
	)
	for price in packing_prices:
		if price.supplier or price.batch_no or (price.customer and price.customer != ctx.get("customer")):
			continue
		if price.uom and price.uom != ctx.uom:
			continue
		if (price.valid_from and getdate(price.valid_from) > getdate(ctx.transaction_date)) or (
			price.valid_upto and getdate(price.valid_upto) < getdate(ctx.transaction_date)
		):
			continue
		if flt(ctx.get("qty")) and number(ctx.qty) % number(price.packing_unit) == 0:
			return True
	if doc and doc.get("custom_spe_keep_manual_rates"):
		if frappe.session.user != "Administrator" and config.manual_rate_role not in frappe.get_roles():
			frappe.throw(
				_("Keeping manual selling rates requires the configured pricing role."),
				frappe.PermissionError,
			)
		return True
	if ctx.get("customer"):
		prices = frappe.get_all(
			"Item Price",
			filters={"price_list": ctx.price_list, "item_code": ctx.item_code, "customer": ctx.customer},
			fields=["uom", "valid_from", "valid_upto", "batch_no"],
		)
		date = getdate(ctx.transaction_date)
		stock_uom = frappe.get_cached_value("Item", ctx.item_code, "stock_uom")
		if any(
			(not p.uom or p.uom in (ctx.uom, stock_uom))
			and not p.batch_no
			and (not p.valid_from or getdate(p.valid_from) <= date)
			and (not p.valid_upto or getdate(p.valid_upto) >= date)
			for p in prices
		):
			return True
	return False


def resolve_response(ctx, native, doc=None):
	ctx = frappe._dict(frappe.parse_json(ctx) if isinstance(ctx, str) else ctx)
	doc = frappe.parse_json(doc) if isinstance(doc, str) else doc
	config = enabled_context(ctx)
	if not config:
		return native
	ctx = frappe._dict(
		{
			**ctx,
			"price_list": ctx.get("price_list") or ctx.get("selling_price_list"),
			"warehouse": native.get("warehouse") or ctx.get("warehouse") or ctx.get("set_warehouse"),
			"uom": native.get("uom") or ctx.get("uom"),
			"item_code": native.get("item_code") or ctx.get("item_code"),
			"transaction_date": (doc.get("transaction_date") or doc.get("posting_date"))
			if doc
			else ctx.get("transaction_date") or ctx.get("posting_date") or today(),
		}
	)
	ctx.transaction_date = ctx.transaction_date or today()
	if (
		not ctx.item_code
		or not ctx.price_list
		or not frappe.db.exists(POLICY, {"company": ctx.company, "price_list": ctx.price_list, "enabled": 1})
	):
		return native
	check_context(ctx.company, ctx.price_list, ctx.warehouse, ctx.item_code)
	item = frappe.get_cached_doc("Item", ctx.item_code)
	if not item.is_sales_item or item.is_fixed_asset or _preserve(ctx, native, doc, config):
		native["custom_spe_price_source"] = None
		native["custom_spe_resolved_price_list"] = None
		native["custom_spe_resolution"] = None
		return native
	ctx.uom = ctx.uom or item.sales_uom or item.stock_uom
	if config.get("enable_phase_2"):
		from av_tools.selling_pricing_engine.locations import resolve

		try:
			resolved = resolve(
				ctx.company,
				ctx.price_list,
				item,
				ctx.uom,
				ctx.transaction_date,
				ctx.warehouse,
				(doc or {}).get("custom_spe_branch") or ctx.get("custom_spe_branch"),
			)
		except ValueError as exc:
			frappe.throw(str(exc))
		rate, source = (resolved["rate"], resolved["source"]) if resolved else (None, None)
		native["custom_spe_resolved_price_list"] = resolved["price_list"] if resolved else None
		native["custom_spe_resolution"] = resolved["resolution"] if resolved else None
	else:
		try:
			price = (
				repository.valid_price(
					repository.price_rows(ctx.company, ctx.price_list, ctx.item_code, ctx.uom, ctx.warehouse),
					ctx.transaction_date,
				)
				if ctx.warehouse
				else None
			)
		except ValueError as exc:
			frappe.throw(str(exc))
		if price:
			rate, source = price.rate, price.name
			if price.currency != frappe.get_cached_value("Price List", ctx.price_list, "currency"):
				frappe.throw(_("Published location price currency does not match the Price List."))
		else:
			standard = repository.standard_price(
				ctx.company, ctx.price_list, item, ctx.uom, ctx.transaction_date
			)
			rate, source = (standard.price_list_rate if standard else None), None
	if rate is None or number(rate) <= 0:
		frappe.throw(
			_("No valid published selling price for {0}. Generate and publish a revision first.").format(
				item.name
			)
		)
	price_currency = frappe.get_cached_value("Price List", ctx.price_list, "currency")
	company_currency = frappe.get_cached_value("Company", ctx.company, "default_currency")
	plc_rate = ctx.get("plc_conversion_rate") or (1 if price_currency == company_currency else 0)
	doc_rate = ctx.get("conversion_rate") or (1 if ctx.get("currency") == company_currency else 0)
	if number(plc_rate) <= 0 or number(doc_rate) <= 0:
		frappe.throw(_("Valid transaction and Price List conversion rates are required."))
	baseline = number(rate) * number(plc_rate) / number(doc_rate)
	adjusted = baseline
	margin_value = flt(native.get("margin_rate_or_amount") or ctx.get("margin_rate_or_amount"))
	margin_type = native.get("margin_type") or ctx.get("margin_type")
	if margin_type == "Percentage":
		adjusted *= 1 + number(margin_value) / 100
	elif margin_type == "Amount":
		adjusted += number(margin_value)
	discount_percent = flt(native.get("discount_percentage") or ctx.get("discount_percentage"))
	discount_amount = flt(native.get("discount_amount") or ctx.get("discount_amount"))
	final = (
		adjusted * (1 - number(discount_percent) / 100)
		if discount_percent
		else adjusted - number(discount_amount)
	)
	native.update(
		{"price_list_rate": float(baseline), "rate": float(final), "custom_spe_price_source": source}
	)
	return native


class SellingPricingMixin:
	def set_missing_item_details(self, for_validate=False):
		# Native server reactivity and API-created documents bypass the RPC override.
		config = enabled_context(self.as_dict())
		result = super().set_missing_item_details(for_validate=for_validate)
		if config:
			apply_document_prices(self)
		return result


def apply_document_prices(doc):
	for row in doc.get("items") or []:
		if not row.item_code:
			continue
		ctx = frappe._dict(
			{
				**doc.as_dict(),
				**row.as_dict(),
				"doctype": doc.doctype,
				"name": doc.name,
				"company": doc.company,
				"child_docname": row.name,
				"price_list": doc.selling_price_list,
				"customer": doc.get("customer")
				or (doc.get("party_name") if doc.get("quotation_to") == "Customer" else None),
				"transaction_type": "selling",
				"transaction_date": doc.get("transaction_date") or doc.get("posting_date") or today(),
			}
		)
		values = resolve_response(ctx, frappe._dict(row.as_dict()), doc)
		for key in PRICE_FIELDS:
			if key in values:
				row.set(key, values[key])


@frappe.whitelist()
def refresh_prices(doc):
	data = frappe.parse_json(doc)
	if data.get("doctype") not in SALES_DOCTYPES:
		frappe.throw(_("Unsupported pricing document."))
	doc = frappe.get_doc(data)
	if doc.doctype not in SALES_DOCTYPES or doc.docstatus != 0:
		frappe.throw(_("Only draft Quotation, Sales Order or Sales Invoice prices can be refreshed."))
	doc.check_permission("create" if doc.is_new() else "write")
	if not enabled_context(doc.as_dict()):
		return []
	apply_document_prices(doc)
	return [
		{
			"name": row.name,
			"item_code": row.item_code,
			"warehouse": row.warehouse,
			"uom": row.uom,
			**{key: row.get(key) for key in PRICE_FIELDS},
		}
		for row in doc.get("items") or []
	]


@frappe.whitelist()
def sales_configuration(company):
	config = settings(company, require_enabled=False)
	return {"enabled": bool(config), "expanded": bool(config and config.get("enable_phase_2"))}
