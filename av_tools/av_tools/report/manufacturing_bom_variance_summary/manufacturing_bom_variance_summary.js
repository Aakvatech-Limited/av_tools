frappe.query_reports["Manufacturing BOM Variance Summary"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "purpose",
			label: __("Purpose"),
			fieldtype: "Select",
			options: "\nManufacture\nRepack",
		},
		{
			fieldname: "production_item",
			label: __("Production Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "item_code",
			label: __("Component Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "bom_no",
			label: __("BOM"),
			fieldtype: "Link",
			options: "BOM",
		},
	],
};
