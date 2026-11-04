frappe.query_reports["Selling Margin by Price List"] = {
	filters: [
		{ fieldname: "page", label: __("Page"), fieldtype: "Int", default: 1 },
		{ fieldname: "page_size", label: __("Items per Page"), fieldtype: "Int", default: 500 },
		{ fieldname: "branch", label: __("Pricing Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "supplier", label: __("Cost Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group", description: __("Required for catalogues above 500 Items; dashboard supports 5,000 SKUs per scope.") },
		{ fieldname: "include_child_groups", label: __("Include Child Item Groups"), fieldtype: "Check" },
		{ fieldname: "brand", label: __("Brand"), fieldtype: "Link", options: "Brand" },
		{ fieldname: "source_doctype", label: __("Cost Source Type"), fieldtype: "Select", options: "\nPurchase Invoice\nPurchase Receipt" },
		{ fieldname: "source_document", label: __("Current Cost Source"), fieldtype: "Dynamic Link", options: "source_doctype" },

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
