from frappe import _

from av_tools.av_tools.report.manufacturing_bom_variance.manufacturing_bom_variance import (
	get_item_summary,
	get_report_summary,
	normalize_filters,
)


def execute(filters=None):
	filters = normalize_filters(filters)
	data = get_item_summary(filters)
	chart = get_chart(data)
	return get_columns(), data, None, chart, get_report_summary_from_summary(filters)


def get_report_summary_from_summary(filters):
	from av_tools.av_tools.report.manufacturing_bom_variance.manufacturing_bom_variance import (
		get_detail_data,
	)

	return get_report_summary(get_detail_data(filters))


def get_chart(data):
	top = sorted(data, key=lambda row: row.absolute_variance_percent, reverse=True)[:10]
	return {
		"data": {
			"labels": [row.item_code for row in top],
			"datasets": [{"name": _("Variance %"), "values": [row.variance_percent for row in top]}],
		},
		"type": "bar",
		"axisOptions": {"xIsSeries": 0},
	}


def get_columns():
	return [
		{
			"label": _("Component"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 170,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 190},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Entries"), "fieldname": "entry_count", "fieldtype": "Int", "width": 80},
		{"label": _("BOM Guided Qty"), "fieldname": "bom_guided_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Actual Qty"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Variance Qty"), "fieldname": "variance_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Variance %"), "fieldname": "variance_percent", "fieldtype": "Percent", "width": 100},
		{
			"label": _("Absolute Variance %"),
			"fieldname": "absolute_variance_percent",
			"fieldtype": "Percent",
			"width": 130,
		},
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
		{"label": _("Over Rows"), "fieldname": "over_consumption_rows", "fieldtype": "Int", "width": 90},
		{"label": _("Under Rows"), "fieldname": "under_consumption_rows", "fieldtype": "Int", "width": 90},
		{"label": _("On Standard"), "fieldname": "on_standard_rows", "fieldtype": "Int", "width": 90},
		{"label": _("Direction"), "fieldname": "variance_direction", "fieldtype": "Data", "width": 130},
	]
