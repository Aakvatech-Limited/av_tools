"""Operational reports on published prices, calculation gaps and immutable history."""

import frappe
from frappe import _
from frappe.utils import getdate, today

from av_tools.selling_pricing_engine import engine, repository
from av_tools.selling_pricing_engine.access import REVISION, SETTINGS, check_context, manager, settings
from av_tools.selling_pricing_engine.calculation import margin, number


def column(name, label, kind="Data", options=None, width=160):
	return {"fieldname": name, "label": _(label), "fieldtype": kind, "options": options, "width": width}


def run_report(name, filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company or not filters.price_list:
		frappe.throw(_("Company and Price List are required."))
	manager(filters.company)
	check_context(filters.company, filters.price_list, filters.warehouse, filters.item_code)
	filters.as_on = str(getdate(filters.as_on or today()))
	if name == "Selling Price Revision History":
		# Turning off the engine must not hide previously published audit evidence.
		config = (
			frappe.get_doc(SETTINGS, filters.company)
			if frappe.db.exists(SETTINGS, filters.company)
			else frappe._dict(max_revision_items=500)
		)
		return history(filters, config)
	config = settings(filters.company)
	policy = repository.policy_for(filters.company, filters.price_list)
	if name == "Location Selling Price Matrix":
		return matrix(filters, config)
	columns = [
		column("item_code", "Item", "Link", "Item"),
		column("warehouse", "Warehouse", "Link", "Warehouse"),
		column("uom", "UOM", "Link", "UOM", 90),
		column("currency", "Currency", "Link", "Currency", 90),
		column("cost_rate", "Latest Permitted Invoice Cost", "Currency", "currency"),
		column("selling_rate", "Published Selling Rate", "Currency", "currency"),
		column("gross_profit", "Gross Profit Per Unit", "Currency", "currency"),
		column("margin_percent", "Published Price Margin %", "Percent"),
		column("proposed_rate", "Proposed Rate", "Currency", "currency"),
		column("proposed_margin", "Proposed Margin %", "Percent"),
		column("minimum_margin", "Minimum Margin %", "Percent"),
		column("price_source", "Calculation Source"),
		column("published_source", "Published Source"),
		column("supplier", "Cost Supplier", "Link", "Supplier"),
		column("source_invoice", "Cost Invoice", "Link", "Purchase Invoice"),
		column("pricing_rule", "Rule", "Link", "Selling Price Rule"),
		column("result", "Proposal Result"),
		column("exception_reason", "Exception", width=320),
	]
	rows = []
	for item in items(filters, config.max_revision_items):
		uom = filters.uom or item.sales_uom or item.stock_uom
		actual, published_source = published(filters, item.name, uom)
		context = {
			"item_code": item.name,
			"warehouse": filters.warehouse,
			"uom": uom,
			"valid_from": filters.as_on,
			"valid_upto": None,
		}
		try:
			row = engine.calculate_row(config, policy, context)
		except (ValueError, frappe.ValidationError) as exc:
			row = {
				**context,
				"result": "Blocked",
				"exception_reason": str(exc),
				"cost_available": 0,
				"currency": frappe.get_cached_value("Price List", filters.price_list, "currency"),
			}
		row["selling_rate"], row["published_source"] = actual, published_source
		known_margin = (
			margin(row.get("cost_rate"), actual) if actual is not None and row.get("cost_available") else None
		)
		row["margin_percent"] = float(known_margin) if known_margin is not None else None
		row["gross_profit"] = (
			float(number(actual) - number(row["cost_rate"])) if known_margin is not None else None
		)
		if name == "Missing Selling Prices" and actual is not None:
			continue
		if name == "Below Minimum Selling Margin" and not (
			(row["result"] == "Blocked" and row.get("proposed_margin") is not None)
			or (known_margin is not None and known_margin < config.minimum_margin)
		):
			continue
		rows.append(row)
	return columns, rows


def items(filters, limit):
	criteria = {"disabled": 0, "is_sales_item": 1, "is_fixed_asset": 0, "has_variants": 0}
	if filters.item_code:
		criteria["name"] = filters.item_code
	rows = frappe.get_list(
		"Item",
		filters=criteria,
		fields=["name", "sales_uom", "stock_uom"],
		order_by="name",
		limit_page_length=limit + 1,
	)
	if len(rows) > limit:
		frappe.throw(
			_(
				"Report exceeds the configured item limit. Select an Item or increase the limit in Selling Price Settings."
			)
		)
	return rows


def published(filters, item, uom):
	price = (
		repository.valid_price(
			repository.price_rows(filters.company, filters.price_list, item, uom, filters.warehouse),
			filters.as_on,
		)
		if filters.warehouse
		else None
	)
	if price:
		return price.rate, "Location override"
	price = repository.standard_price(
		filters.company, filters.price_list, frappe.get_cached_doc("Item", item), uom, filters.as_on
	)
	return (
		(price.price_list_rate, "Standard fallback" if filters.warehouse else "Standard Item Price")
		if price
		else (None, "Missing")
	)


def matrix(filters, config):
	criteria = {"company": filters.company, "is_group": 0, "disabled": 0}
	if filters.warehouse:
		criteria["name"] = filters.warehouse
	warehouses = frappe.get_list(
		"Warehouse", filters=criteria, pluck="name", order_by="name", limit_page_length=26
	)
	if len(warehouses) > 25:
		frappe.throw(_("Select a Warehouse to keep the matrix within 25 permitted locations."))
	columns = [
		column("item_code", "Item", "Link", "Item", 200),
		column("uom", "UOM", "Link", "UOM", 90),
		column("currency", "Currency", "Link", "Currency", 90),
	]
	for index, wh in enumerate(warehouses):
		columns += [
			column(f"rate_{index}", wh, "Currency", "currency", 140),
			column(f"source_{index}", wh + " Source", width=150),
		]
	rows = []
	for item in items(filters, config.max_revision_items):
		row = {
			"item_code": item.name,
			"uom": filters.uom or item.sales_uom or item.stock_uom,
			"currency": frappe.get_cached_value("Price List", filters.price_list, "currency"),
		}
		for index, wh in enumerate(warehouses):
			context = frappe._dict({**filters, "warehouse": wh})
			row[f"rate_{index}"], row[f"source_{index}"] = published(context, item.name, row["uom"])
		rows.append(row)
	return columns, rows


def history(filters, config):
	columns = [
		column("revision", "Revision", "Link", REVISION, 210),
		column("item_code", "Item", "Link", "Item"),
		column("warehouse", "Warehouse", "Link", "Warehouse"),
		column("uom", "UOM", "Link", "UOM", 90),
		column("currency", "Currency", "Link", "Currency", 90),
		column("previous_rate", "Previous Rate", "Currency", "currency"),
		column("proposed_rate", "Published Rate", "Currency", "currency"),
		column("cost_rate", "Calculation Cost", "Currency", "currency"),
		column("proposed_margin", "Calculated Margin %", "Percent"),
		column("price_source", "Source"),
		column("pricing_rule", "Rule", "Link", "Selling Price Rule"),
		column("source_invoice", "Invoice", "Link", "Purchase Invoice"),
		column("published_on", "Published On", "Datetime"),
		column("published_by", "Published By", "Link", "User"),
		column("review_note", "Review Note", width=280),
	]
	criteria = {
		"company": filters.company,
		"price_list": filters.price_list,
		"docstatus": 1,
		"valid_from": ["<=", filters.as_on],
	}
	parents = frappe.get_list(
		REVISION,
		filters=criteria,
		pluck="name",
		order_by="published_on desc",
		limit_page_length=config.max_revision_items + 1,
	)
	if len(parents) > config.max_revision_items:
		frappe.throw(_("History exceeds the configured revision limit."))
	rows = []
	for name in parents:
		doc = frappe.get_doc(REVISION, name)
		doc.check_permission("read")
		for line in doc.items:
			if line.result != "Published" or any(
				filters.get(key) and filters.get(key) != line.get(key)
				for key in ("warehouse", "item_code", "uom")
			):
				continue
			check_context(doc.company, doc.price_list, line.warehouse, line.item_code)
			row = line.as_dict()
			if not line.cost_available:
				row["cost_rate"] = row["proposed_margin"] = None
			rows.append(
				{
					**row,
					"revision": doc.name,
					"published_on": doc.published_on,
					"published_by": doc.published_by,
				}
			)
			if len(rows) > 5000:
				frappe.throw(_("History exceeds 5,000 rows. Narrow the Item or Warehouse filter."))
	return columns, rows
