import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today


DEFAULT_DAYS = 30
SUPPORTED_PURPOSES = ("Manufacture", "Repack")


def execute(filters=None):
	filters = normalize_filters(filters)
	data = get_detail_data(filters)
	return get_columns(), data, None, None, get_report_summary(data)


def normalize_filters(filters=None):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	filters = frappe._dict(filters or {})
	filters.company = filters.get("company") or frappe.defaults.get_user_default("Company")
	filters.from_date = getdate(filters.get("from_date") or add_days(today(), -(DEFAULT_DAYS - 1)))
	filters.to_date = getdate(filters.get("to_date") or today())

	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be after To Date."))

	return filters


def get_detail_data(filters=None):
	filters = normalize_filters(filters)
	frappe.has_permission("Stock Entry", "read", throw=True)

	stock_entry = frappe.qb.DocType("Stock Entry")
	detail = frappe.qb.DocType("Stock Entry Detail")
	bom = frappe.qb.DocType("BOM")
	item = frappe.qb.DocType("Item")

	query = (
		frappe.qb.from_(stock_entry)
		.inner_join(detail)
		.on(detail.parent == stock_entry.name)
		.left_join(bom)
		.on(bom.name == stock_entry.bom_no)
		.left_join(item)
		.on(item.name == detail.item_code)
		.select(
			stock_entry.name.as_("stock_entry"),
			stock_entry.posting_date,
			stock_entry.company,
			stock_entry.purpose,
			stock_entry.bom_no,
			stock_entry.work_order,
			stock_entry.fg_completed_qty,
			bom.item.as_("production_item"),
			detail.item_code,
			item.item_name,
			detail.uom,
			detail.stock_uom,
			detail.is_finished_item,
			detail.is_scrap_item,
			detail.qty.as_("actual_transaction_qty"),
			detail.transfer_qty.as_("actual_qty"),
			detail.bom_guided_qty,
			detail.bom_guided_stock_qty,
		)
		.where(stock_entry.docstatus == 1)
		.where(stock_entry.purpose.isin(SUPPORTED_PURPOSES))
		.where(detail.bom_guided_stock_qty.isnotnull())
		.where(stock_entry.posting_date >= filters.from_date)
		.where(stock_entry.posting_date <= filters.to_date)
	)

	if filters.company:
		query = query.where(stock_entry.company == filters.company)
	if filters.get("purpose"):
		query = query.where(stock_entry.purpose == filters.purpose)
	if filters.get("production_item"):
		query = query.where(bom.item == filters.production_item)
	if filters.get("item_code"):
		query = query.where(detail.item_code == filters.item_code)
	if filters.get("bom_no"):
		query = query.where(stock_entry.bom_no == filters.bom_no)
	if filters.get("stock_entry"):
		query = query.where(stock_entry.name == filters.stock_entry)
	if filters.get("work_order"):
		query = query.where(stock_entry.work_order == filters.work_order)

	rows = query.orderby(stock_entry.posting_date).orderby(stock_entry.name).run(as_dict=True)

	for row in rows:
		actual = flt(row.actual_qty)
		guided = flt(row.bom_guided_stock_qty)
		row.row_category = "Finished Goods" if row.is_finished_item else ("Scrap / By-product" if row.is_scrap_item else "Consumption")
		row.transaction_variance_qty = flt(row.actual_transaction_qty) - flt(row.bom_guided_stock_qty)
		row.variance_qty = actual - guided
		row.variance_percent = row.variance_qty / guided * 100 if guided else 0
		row.consumption_index_percent = actual / guided * 100 if guided else 0
		row.efficiency_percent = guided / actual * 100 if actual else 0
		row.variance_direction = get_variance_direction(row.variance_percent, row.row_category)

	return rows


def get_variance_direction(variance_percent, category="Consumption"):
	if variance_percent > 0:
		return _("Over Consumption") if category == "Consumption" else _("Above Expected")
	if variance_percent < 0:
		return _("Under Consumption") if category == "Consumption" else _("Below Expected")
	return _("On Standard")


def get_item_summary(filters=None):
	rows = get_detail_data(filters)
	grouped = {}

	for row in rows:
		key = (row.row_category, row.item_code, row.stock_uom)
		summary = grouped.setdefault(
			key,
			frappe._dict(
				row_category=row.row_category,
				item_code=row.item_code,
				item_name=row.item_name,
				uom=row.stock_uom,
				actual_qty=0.0,
				bom_guided_qty=0.0,
				absolute_variance_qty=0.0,
				entry_names=set(),
				over_consumption_rows=0,
				under_consumption_rows=0,
				on_standard_rows=0,
			),
		)

		summary.actual_qty += flt(row.actual_qty)
		summary.bom_guided_qty += flt(row.bom_guided_stock_qty)
		summary.absolute_variance_qty += abs(flt(row.variance_qty))
		summary.entry_names.add(row.stock_entry)

		if row.variance_percent > 0:
			summary.over_consumption_rows += 1
		elif row.variance_percent < 0:
			summary.under_consumption_rows += 1
		else:
			summary.on_standard_rows += 1

	result = []
	for summary in grouped.values():
		summary.entry_count = len(summary.entry_names)
		del summary["entry_names"]
		summary.variance_qty = summary.actual_qty - summary.bom_guided_qty
		summary.variance_percent = (
			summary.variance_qty / summary.bom_guided_qty * 100 if summary.bom_guided_qty else 0
		)
		summary.absolute_variance_percent = (
			summary.absolute_variance_qty / summary.bom_guided_qty * 100
			if summary.bom_guided_qty
			else 0
		)
		summary.consumption_index_percent = (
			summary.actual_qty / summary.bom_guided_qty * 100 if summary.bom_guided_qty else 0
		)
		summary.efficiency_percent = (
			summary.bom_guided_qty / summary.actual_qty * 100 if summary.actual_qty else 0
		)
		summary.variance_direction = get_variance_direction(summary.variance_percent, summary.row_category)
		result.append(summary)

	return sorted(result, key=lambda row: row.absolute_variance_percent, reverse=True)


def get_monthly_summary(filters=None):
	rows = get_detail_data(filters)
	grouped = {}

	for row in rows:
		month = row.posting_date.strftime("%Y-%m")
		key = (month, row.row_category, row.item_code, row.stock_uom)
		summary = grouped.setdefault(
			key,
			{"month": month, "actual": 0.0, "guided": 0.0, "absolute_variance": 0.0},
		)
		summary["actual"] += flt(row.actual_qty)
		summary["guided"] += flt(row.bom_guided_stock_qty)
		summary["absolute_variance"] += abs(flt(row.variance_qty))

	monthly = {}
	for values in grouped.values():
		stats = monthly.setdefault(
			values["month"],
			{"efficiency_values": [], "absolute_variance_values": [], "consumption_values": []},
		)
		if values["actual"]:
			stats["efficiency_values"].append(values["guided"] / values["actual"] * 100)
		if values["guided"]:
			stats["absolute_variance_values"].append(
				values["absolute_variance"] / values["guided"] * 100
			)
			stats["consumption_values"].append(values["actual"] / values["guided"] * 100)

	result = []
	for month, stats in sorted(monthly.items()):
		result.append(
			frappe._dict(
				month=month,
				efficiency_percent=_average(stats["efficiency_values"]),
				absolute_variance_percent=_average(stats["absolute_variance_values"]),
				consumption_index_percent=_average(stats["consumption_values"]),
			)
		)
	return result


def get_report_summary(detail_rows):
	item_summary = summarize_detail_rows(detail_rows)
	entry_count = len({row.stock_entry for row in detail_rows})
	average_efficiency = _average([row.efficiency_percent for row in item_summary])
	average_abs_variance = _average([row.absolute_variance_percent for row in item_summary])
	over_items = sum(1 for row in item_summary if row.variance_percent > 0)

	return [
		{"value": entry_count, "indicator": "Blue", "label": _("Stock Entries"), "datatype": "Int"},
		{
			"value": average_efficiency,
			"indicator": "Green" if average_efficiency >= 100 else "Orange",
			"label": _("Avg BOM Efficiency"),
			"datatype": "Percent",
		},
		{
			"value": average_abs_variance,
			"indicator": "Orange" if average_abs_variance else "Green",
			"label": _("Avg Absolute Variance"),
			"datatype": "Percent",
		},
		{
			"value": over_items,
			"indicator": "Red" if over_items else "Green",
			"label": _("Over-Consumed Items"),
			"datatype": "Int",
		},
	]


def summarize_detail_rows(detail_rows):
	grouped = {}
	for row in detail_rows:
		key = (row.row_category, row.item_code, row.stock_uom)
		summary = grouped.setdefault(
			key,
			frappe._dict(
				row_category=row.row_category,
				item_code=row.item_code,
				uom=row.stock_uom,
				actual_qty=0.0,
				bom_guided_qty=0.0,
				absolute_variance_qty=0.0,
			),
		)
		summary.actual_qty += flt(row.actual_qty)
		summary.bom_guided_qty += flt(row.bom_guided_stock_qty)
		summary.absolute_variance_qty += abs(flt(row.variance_qty))

	result = []
	for row in grouped.values():
		row.variance_qty = row.actual_qty - row.bom_guided_qty
		row.variance_percent = row.variance_qty / row.bom_guided_qty * 100 if row.bom_guided_qty else 0
		row.absolute_variance_percent = (
			row.absolute_variance_qty / row.bom_guided_qty * 100 if row.bom_guided_qty else 0
		)
		row.efficiency_percent = row.bom_guided_qty / row.actual_qty * 100 if row.actual_qty else 0
		result.append(row)
	return result


def _average(values):
	values = [flt(value) for value in values if value is not None]
	return sum(values) / len(values) if values else 0


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{
			"label": _("Stock Entry"),
			"fieldname": "stock_entry",
			"fieldtype": "Link",
			"options": "Stock Entry",
			"width": 180,
		},
		{"label": _("Purpose"), "fieldname": "purpose", "fieldtype": "Data", "width": 110},
		{
			"label": _("Work Order"),
			"fieldname": "work_order",
			"fieldtype": "Link",
			"options": "Work Order",
			"width": 160,
		},
		{"label": _("BOM"), "fieldname": "bom_no", "fieldtype": "Link", "options": "BOM", "width": 160},
		{
			"label": _("Production Item"),
			"fieldname": "production_item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 160,
		},
		{
			"label": _("Component"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 160,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Row UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Category"), "fieldname": "row_category", "fieldtype": "Data", "width": 140},
		{"label": _("BOM Guided Qty"), "fieldname": "bom_guided_qty", "fieldtype": "Float", "width": 120},
		{"label": _("BOM Guided Stock Qty"), "fieldname": "bom_guided_stock_qty", "fieldtype": "Float", "width": 155},
		{"label": _("Actual Qty"), "fieldname": "actual_transaction_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Actual Stock Qty"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 145},
		{"label": _("Transaction Variance Qty"), "fieldname": "transaction_variance_qty", "fieldtype": "Float", "width": 145},
		{"label": _("Variance Qty"), "fieldname": "variance_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Variance %"), "fieldname": "variance_percent", "fieldtype": "Percent", "width": 100},
		{
			"label": _("Consumption Index %"),
			"fieldname": "consumption_index_percent",
			"fieldtype": "Percent",
			"width": 125,
		},
		{
			"label": _("BOM Efficiency %"),
			"fieldname": "efficiency_percent",
			"fieldtype": "Percent",
			"width": 120,
		},
		{"label": _("Direction"), "fieldname": "variance_direction", "fieldtype": "Data", "width": 130},
	]
