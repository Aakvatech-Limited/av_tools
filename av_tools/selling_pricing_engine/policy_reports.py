"""Phase 2 operational comparisons; amounts always retain their own currency."""

import frappe
from frappe import _
from frappe.utils import getdate, today

from av_tools.selling_pricing_engine import cost_sources, reports, repository
from av_tools.selling_pricing_engine.access import check_context, manager, settings
from av_tools.selling_pricing_engine.policies import check_filters
from av_tools.selling_pricing_engine.report_scope import catalog, detail_message


def run(name, filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company or not filters.price_list:
		frappe.throw(_("Company and Price List are required."))
	manager(filters.company)
	check_context(filters.company, filters.price_list, filters.warehouse, filters.item_code)
	check_filters(filters)
	config = settings(filters.company)
	if filters.price_list:
		repository.policy_for(filters.company, filters.price_list)
	if not config.get("enable_phase_2"):
		frappe.throw(_("Enable Expanded Pricing Policies to use this report."))
	filters.as_on = str(getdate(filters.as_on or today()))
	scope_items = catalog(filters)
	if name == "Supplier Cost Comparison":
		return supplier_comparison(filters, config)
	if name == "Selling Price Fallback Usage":
		columns, rows, message = reports.history(filters, config, fallback_only=True)
		columns += [
			reports.column("fallback_price_list", "Fallback Price List", "Link", "Price List"),
		]
		return columns, rows, message
	# Reuse the exact pricing/margin calculation rather than an independent margin formula.
	if name == "Selling Margin by Location":
		criteria = {"company": filters.company, "disabled": 0, "is_group": 0}
		if filters.warehouse:
			criteria["name"] = filters.warehouse
		if filters.branch:
			criteria["custom_spe_branch"] = filters.branch
		locations = frappe.get_list("Warehouse", filters=criteria, pluck="name", limit_page_length=26)
		if len(locations) > 25:
			frappe.throw(_("Select a Branch or Warehouse to compare at most 25 locations."))
		if len(scope_items) > 500 and len(locations) > 1:
			frappe.throw(_("Select one Warehouse for large Item Group margin comparisons."))
		contexts = [frappe._dict({**filters, "warehouse": warehouse}) for warehouse in locations]
	else:
		contexts = [filters]
	rows, columns = [], []
	message = detail_message(filters)
	for context in contexts:
		columns, result, message = reports.run_report("Selling Price and Margin Review", context)
		for row in result:
			row["price_list"] = context.price_list
		rows.extend(result)
		if len(rows) > 5000:
			frappe.throw(_("Margin comparison exceeds 5,000 rows. Narrow the filters."))
	return [reports.column("price_list", "Price List", "Link", "Price List"), *columns], rows, message


def supplier_comparison(filters, config):
	doctype = filters.get("source_doctype") or "Purchase Invoice"
	if doctype not in ("Purchase Invoice", "Purchase Receipt"):
		frappe.throw(_("Select Purchase Invoice or Purchase Receipt."))
	frappe.has_permission(doctype, "read", throw=True)
	items = reports.items(filters, config.max_revision_items)
	if not items:
		return [], []
	criteria = [
		[doctype, "company", "=", filters.company],
		[doctype, "docstatus", "=", 1],
		[doctype, "is_return", "=", 0],
		[doctype, "posting_date", "<=", filters.as_on],
		[doctype + " Item", "item_code", "in", [item.name for item in items]],
	]
	if filters.supplier:
		criteria.append([doctype, "supplier", "=", filters.supplier])
	names = frappe.get_list(
		doctype,
		filters=criteria,
		fields=["name"],
		distinct=True,
		order_by="posting_date desc, creation desc, name desc",
		limit_page_length=5001,
	)
	if len(names) > 5000:
		frappe.throw(_("Supplier comparison exceeds 5,000 source documents. Select an Item or Supplier."))
	currency = frappe.get_cached_value("Price List", filters.price_list, "currency")
	eligible = {item.name: item for item in items}
	seen, rows = set(), []
	for source in names:
		doc = frappe.get_doc(doctype, source.name)
		doc.check_permission("read")
		if not frappe.has_permission("Supplier", "select", doc=doc.supplier):
			continue
		for line in sorted(doc.items, key=lambda row: row.idx, reverse=True):
			key = (line.item_code, doc.supplier)
			if (
				line.item_code not in eligible
				or key in seen
				or line.stock_qty <= 0
				or line.base_net_amount <= 0
			):
				continue
			seen.add(key)
			item = frappe.get_cached_doc("Item", line.item_code)
			uom = filters.uom or item.sales_uom or item.stock_uom
			cost = cost_sources.submitted(
				filters.company,
				item,
				uom,
				currency,
				filters.as_on,
				doctype,
				{"supplier": doc.supplier, "source_document": doc.name},
				current=True,
			)
			rows.append(
				{"item_code": item.name, "supplier": doc.supplier, "uom": uom, "currency": currency, **cost}
			)
			if len(rows) > 5000:
				frappe.throw(_("Supplier comparison exceeds 5,000 rows. Narrow the filters."))
	columns = [
		reports.column("item_code", "Item", "Link", "Item"),
		reports.column("supplier", "Supplier", "Link", "Supplier"),
		reports.column("uom", "UOM", "Link", "UOM"),
		reports.column("currency", "Currency", "Link", "Currency"),
		reports.column("cost_rate", "Comparable Purchase Cost", "Currency", "currency"),
		reports.column("cost_date", "Purchase Date", "Date"),
		reports.column("source_doctype", "Source Type", "Link", "DocType"),
		reports.column("source_document", "Source", "Dynamic Link", "source_doctype"),
	]
	return columns, rows, detail_message(filters)
