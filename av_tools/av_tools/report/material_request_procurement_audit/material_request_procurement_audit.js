// Copyright (c) 2026, Aakvatech and contributors
// For license information, please see license.txt

frappe.query_reports["Material Request Procurement Audit"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "time_span",
			label: __("MR Date Range"),
			fieldtype: "Select",
			options: [
				"Today",
				"Yesterday",
				"This Week",
				"Last Week",
				"This Month",
				"Last Month",
				"This Year",
				"Last Year",
				"Period",
				"All",
			],
			default: "This Month",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			depends_on: "eval:doc.time_span == 'Period'",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			depends_on: "eval:doc.time_span == 'Period'",
		},
		{
			fieldname: "material_request",
			label: __("Material Request"),
			fieldtype: "Link",
			options: "Material Request",
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "procurement_status",
			label: __("Procurement Status"),
			fieldtype: "Select",
			options: [
				"All",
				"Not Ordered",
				"Partly Ordered",
				"Fully Ordered",
				"Partly Received",
				"Fully Received",
				"Over Ordered",
				"Over Received",
			],
			default: "All",
		},
		{
			fieldname: "show_only_exceptions",
			label: __("Show Only Audit Exceptions"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
