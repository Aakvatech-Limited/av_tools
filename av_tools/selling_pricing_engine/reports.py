"""Operational reports on published prices, calculation gaps and immutable history."""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, getdate, today

from av_tools.selling_pricing_engine import engine, repository
from av_tools.selling_pricing_engine.access import REVISION, SETTINGS, check_context, manager, settings
from av_tools.selling_pricing_engine.calculation import margin, number
from av_tools.selling_pricing_engine.coverage import PublishedCoverage
from av_tools.selling_pricing_engine.report_scope import (
	catalog,
	detail_items,
	detail_message,
	permitted_names,
	read_rows,
	revision_children,
)


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
	if not config.get("enable_phase_2") and any(
		filters.get(key) for key in ("branch", "supplier", "source_document")
	):
		frappe.throw(_("Enable Expanded Pricing Policies before using Phase 2 filters."))
	filters.phase_2 = bool(config.get("enable_phase_2"))
	policy = repository.policy_for(filters.company, filters.price_list)
	if name == "Location Selling Price Matrix":
		return matrix(filters, config)
	columns = [
		column("item_code", "Item", "Link", "Item"),
		column("warehouse", "Warehouse", "Link", "Warehouse"),
		column("branch", "Branch", "Link", "Branch"),
		column("uom", "UOM", "Link", "UOM", 90),
		column("currency", "Currency", "Link", "Currency", 90),
		column("cost_rate", "Comparable Cost", "Currency", "currency"),
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
		column("source_doctype", "Cost Source Type", "Link", "DocType"),
		column("source_document", "Cost Source", "Dynamic Link", "source_doctype"),
		column("pricing_rule", "Rule", "Link", "Selling Price Rule"),
		column("result", "Proposal Result"),
		column("exception_reason", "Exception", width=320),
	]
	rows = []
	page_items = items(filters, config.max_revision_items)
	reader = PublishedCoverage(filters, config, items=page_items)
	for item in page_items:
		uom = filters.uom or item.sales_uom or item.stock_uom
		view_item = frappe._dict({**item, "sales_uom": uom})
		published_source, actual = reader.resolve(view_item, filters.price_list, with_rate=True)
		if name == "Missing Selling Prices" and actual is not None:
			continue
		context = {
			"item_code": item.name,
			"warehouse": filters.warehouse,
			"uom": uom,
			"valid_from": filters.as_on,
			"valid_upto": None,
		}
		if filters.phase_2:
			context.update(
				{key: filters.get(key) for key in ("branch", "supplier", "source_doctype", "source_document")}
			)
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
		if name == "Below Minimum Selling Margin" and not (
			(row["result"] == "Blocked" and row.get("proposed_margin") is not None)
			or (known_margin is not None and known_margin < config.minimum_margin)
		):
			continue
		rows.append(row)
	return columns, rows, detail_message(filters)


def items(filters, limit):
	# Live proposals retrieve procurement evidence. Keep each foreground report
	# bounded even if Max Revision Items is configured for a 5,000-SKU batch.
	return detail_items(filters, limit=min(int(limit), 500))


def published(filters, item, uom):
	if filters.get("phase_2"):
		from av_tools.selling_pricing_engine.locations import resolve

		result = resolve(
			filters.company,
			filters.price_list,
			frappe.get_cached_doc("Item", item),
			uom,
			filters.as_on,
			filters.warehouse,
			filters.get("branch"),
		)
		return (result["rate"], result["resolution"]) if result else (None, "Missing")
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
	if filters.get("branch"):
		criteria["custom_spe_branch"] = filters.branch
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
	page_items = items(filters, config.max_revision_items)
	if filters.get("_scope_total", 0) > 500 and len(warehouses) > 1:
		frappe.throw(_("Select one Warehouse for a large Item Group price matrix."))
	readers = [
		PublishedCoverage(frappe._dict({**filters, "warehouse": warehouse}), config, items=page_items)
		for warehouse in warehouses
	]
	for item in page_items:
		uom = filters.uom or item.sales_uom or item.stock_uom
		view_item = frappe._dict({**item, "sales_uom": uom})
		row = {
			"item_code": item.name,
			"uom": uom,
			"currency": frappe.get_cached_value("Price List", filters.price_list, "currency"),
		}
		for index, reader in enumerate(readers):
			try:
				row[f"source_{index}"], row[f"rate_{index}"] = reader.resolve(
					view_item, filters.price_list, with_rate=True
				)
			except ValueError as exc:
				row[f"source_{index}"], row[f"rate_{index}"] = str(exc), None
		rows.append(row)
	return columns, rows, detail_message(filters)


def history(filters, config, *, fallback_only=False):
	columns = [
		column("revision", "Revision", "Link", REVISION, 210),
		column("item_code", "Item", "Link", "Item"),
		column("warehouse", "Warehouse", "Link", "Warehouse"),
		column("branch", "Branch", "Link", "Branch"),
		column("uom", "UOM", "Link", "UOM", 90),
		column("currency", "Currency", "Link", "Currency", 90),
		column("previous_rate", "Previous Rate", "Currency", "currency"),
		column("proposed_rate", "Published Rate", "Currency", "currency"),
		column("cost_rate", "Calculation Cost", "Currency", "currency"),
		column("proposed_margin", "Calculated Margin %", "Percent"),
		column("price_source", "Source"),
		column("pricing_rule", "Rule", "Link", "Selling Price Rule"),
		column("source_doctype", "Cost Source Type", "Link", "DocType"),
		column("source_document", "Cost Source", "Dynamic Link", "source_doctype"),
		column("published_on", "Published On", "Datetime"),
		column("published_by", "Published By", "Link", "User"),
		column("review_note", "Review Note", width=280),
	]
	item_ids = [item.name for item in catalog(filters, historical=True)]
	start = str(getdate(filters.get("from_date") or add_months(getdate(filters.as_on).replace(day=1), -5)))
	if start > filters.as_on:
		frappe.throw(_("From Date cannot be later than the effective date."))
	parents = read_rows(
		REVISION,
		filters={
			"company": filters.company,
			"price_list": filters.price_list,
			"docstatus": 1,
			"valid_from": ["<=", filters.as_on],
			"published_on": ["between", [start, add_days(filters.as_on, 1)]],
		},
		fields=["name", "published_on", "published_by"],
	)
	parents = [row for row in parents if getdate(row.published_on) <= getdate(filters.as_on)]
	criteria = {"result": "Published", "item_code": ["in", item_ids]}
	for key in ("warehouse", "branch", "uom", "supplier"):
		if filters.get(key):
			criteria[key] = filters[key]
	if fallback_only:
		criteria["price_source"] = ["in", ["Base Price Fallback", "Standard Price Fallback"]]
	fields = [
		"parent",
		"item_code",
		"warehouse",
		"branch",
		"supplier",
		"uom",
		"currency",
		"previous_rate",
		"proposed_rate",
		"cost_rate",
		"cost_available",
		"proposed_margin",
		"price_source",
		"pricing_rule",
		"source_doctype",
		"source_document",
		"source_invoice",
		"review_note",
		"fallback_price_list",
	]
	lines = revision_children([parent.name for parent in parents], filters=criteria, fields=fields)
	links = (
		("item_code", "Item"),
		("warehouse", "Warehouse"),
		("branch", "Branch"),
		("supplier", "Supplier"),
	)
	allowed = {key: permitted_names(doctype, [line.get(key) for line in lines]) for key, doctype in links}
	headers = {parent.name: parent for parent in parents}
	rows = []
	for line in lines:
		if not all(not line.get(key) or line.get(key) in allowed[key] for key, _dt in links):
			continue
		row = dict(line)
		if not line.cost_available:
			row["cost_rate"] = row["proposed_margin"] = None
		header = headers[line.parent]
		row.update(revision=line.parent, published_on=header.published_on, published_by=header.published_by)
		rows.append(row)
	rows.sort(key=lambda row: (str(row["published_on"]), row["revision"], row["item_code"]), reverse=True)
	try:
		page, size = int(filters.get("page") or 1), int(filters.get("page_size") or 500)
	except (TypeError, ValueError):
		frappe.throw(_("Use whole numbers for Page and Records per Page."))
	if page < 1 or not 1 <= size <= 500:
		frappe.throw(_("Use a positive Page and at most 500 history records per page."))
	message = _(
		"Price List / Item Group history from {0}: page {1}, {2} records per page, {3} permitted records in this date range. No audit snapshots are loaded."
	).format(start, page, size, len(rows))
	return columns, rows[(page - 1) * size : page * size], message
