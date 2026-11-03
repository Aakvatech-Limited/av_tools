frappe.query_reports["Selling Price Revision History"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "price_list",
			label: __("Price List"),
			fieldtype: "Link",
			options: "Price List",
			reqd: 1,
			get_query: () => ({ filters: { selling: 1, enabled: 1 } }),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({
				filters: {
					company: frappe.query_report.get_filter_value("company"),
					is_group: 0,
					disabled: 0,
				},
			}),
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{ fieldname: "uom", label: __("UOM"), fieldtype: "Link", options: "UOM" },
		{
			fieldname: "as_on",
			label: __("Price Effective As On"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
	],
};
