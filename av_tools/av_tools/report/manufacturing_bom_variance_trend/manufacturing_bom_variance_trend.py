from frappe import _

from av_tools.av_tools.report.manufacturing_bom_variance.manufacturing_bom_variance import (
	get_monthly_summary,
	normalize_filters,
)


def execute(filters=None):
	filters = normalize_filters(filters)
	data = get_monthly_summary(filters)
	return get_columns(), data, None, get_chart(data)


def get_chart(data):
	return {
		"data": {
			"labels": [row.month for row in data],
			"datasets": [
				{"name": _("BOM Efficiency %"), "values": [row.efficiency_percent for row in data]},
				{
					"name": _("Absolute Variance %"),
					"values": [row.absolute_variance_percent for row in data],
				},
			],
		},
		"type": "line",
		"axisOptions": {"xIsSeries": 1},
	}


def get_columns():
	return [
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 110},
		{
			"label": _("BOM Efficiency %"),
			"fieldname": "efficiency_percent",
			"fieldtype": "Percent",
			"width": 130,
		},
		{
			"label": _("Consumption Index %"),
			"fieldname": "consumption_index_percent",
			"fieldtype": "Percent",
			"width": 130,
		},
		{
			"label": _("Absolute Variance %"),
			"fieldname": "absolute_variance_percent",
			"fieldtype": "Percent",
			"width": 140,
		},
	]
