"""Bound interactive analytics by catalogue scope, not by historical price-row count."""

import frappe
from frappe import _
from frappe.utils import getdate

from av_tools.selling_pricing_engine.policies import item_filters

SKU_LIMIT = 5000
DETAIL_LIMIT = 500
PAGE_SIZE = 500
RECORD_LIMIT = 100000


def chunks(values, size=PAGE_SIZE):
	for start in range(0, len(values), size):
		yield values[start : start + size]


def read_rows(doctype, *, fields, filters, limit=RECORD_LIMIT, **kwargs):
	"""Permission-filtered pages. Never silently truncate an aggregate."""
	rows = []
	while True:
		page = frappe.get_list(
			doctype,
			fields=fields,
			filters=filters,
			limit_start=len(rows),
			limit_page_length=PAGE_SIZE,
			order_by="name",
			**kwargs,
		)
		rows.extend(page)
		if len(rows) > limit:
			frappe.throw(
				_(
					"This pricing view exceeds its record limit. Narrow the Price List, Item Group, Warehouse or Item."
				)
			)
		if len(page) < PAGE_SIZE:
			return rows


def catalog(filters, *, limit=SKU_LIMIT, historical=False):
	criteria = item_filters(filters)
	if historical:
		for key in ("disabled", "is_sales_item", "is_fixed_asset", "has_variants"):
			criteria.pop(key, None)
	rows = frappe.get_list(
		"Item",
		filters=criteria,
		fields=["name", "item_group", "sales_uom", "stock_uom", "end_of_life"],
		order_by="name",
		limit_page_length=limit + 1,
	)
	if not filters.get("item_group") and not filters.get("item_code") and len(rows) > DETAIL_LIMIT:
		frappe.throw(
			_(
				"Select an Item Group for this Price List: the catalogue contains more than 500 sellable Items. Large pricing charts and reports run per Price List / Item Group."
			)
		)
	if len(rows) > limit:
		frappe.throw(
			_(
				"This Item Group is too large for this view. Select a smaller Item Group, Brand or Item. Dashboard coverage supports 5,000 SKUs; live cost/margin detail reports support 500 Items per request."
			)
		)
	date = getdate(filters.get("as_on"))
	return (
		rows
		if historical
		else [row for row in rows if not row.end_of_life or getdate(row.end_of_life) >= date]
	)


def permitted_names(doctype, names):
	"""Resolve User Permissions once per name batch instead of once per row."""
	allowed = set()
	for batch in chunks(sorted({name for name in names if name})):
		allowed.update(
			frappe.get_list(doctype, filters={"name": ["in", batch]}, pluck="name", limit_page_length=0)
		)
	return allowed


def detail_items(filters, *, limit=DETAIL_LIMIT):
	items = catalog(filters)
	try:
		page = int(filters.get("page") or 1)
		size = int(filters.get("page_size") or min(limit, DETAIL_LIMIT))
	except (TypeError, ValueError):
		frappe.throw(_("Page and Items per Page must be whole numbers."))
	if page < 1 or not 1 <= size <= min(limit, DETAIL_LIMIT):
		frappe.throw(_("Use a positive Page and at most 500 Items per Page (within Max Revision Items)."))
	filters["_scope_total"], filters["_scope_page"], filters["_scope_size"] = len(items), page, size
	return items[(page - 1) * size : page * size]


def detail_message(filters):
	return _(
		"Price List / Item Group detail: page {0}, at most {1} Items per page, {2} eligible Items in this scope. Exception reports filter this page; these are not catalogue-wide totals. Use the dashboard for full scoped counts."
	).format(
		filters.get("_scope_page") or 1,
		filters.get("_scope_size") or DETAIL_LIMIT,
		filters.get("_scope_total") or 0,
	)


def revision_children(parent_names, *, fields, filters=None):
	rows = []
	for batch in chunks(parent_names):
		criteria = {
			**(filters or {}),
			"parent": ["in", batch],
			"parenttype": "Selling Price Revision",
			"parentfield": "items",
		}
		start = 0
		while True:
			page = frappe.get_all(
				"Selling Price Revision Item",
				filters=criteria,
				fields=fields,
				order_by="name",
				limit_start=start,
				limit_page_length=PAGE_SIZE,
			)
			rows.extend(page)
			if len(rows) > RECORD_LIMIT:
				frappe.throw(
					_(
						"Revision history exceeds 100,000 scoped rows. Narrow the Price List / Item Group, date range or Warehouse."
					)
				)
			start += len(page)
			if len(page) < PAGE_SIZE:
				break
	return rows
