frappe.query_reports["Selling Pricing Manager Overview"] = {
	onload(report) {
		if (!report.page?.add_inner_button) return;
		report.page.add_inner_button(__("Use Scope for Dashboard"), async () => {
			await frappe.xcall("av_tools.selling_pricing_engine.dashboard.save_dashboard_scope", {
				filters: report.get_filter_values(),
			});
			frappe.msgprint(
				__(
					"Your dashboard now uses this Company, Price List and Item Group scope. Reload the dashboard. Explicit widget filters take precedence; its effective date remains dynamic."
				)
			);
		});
		report.page.add_inner_button(__("Reset Dashboard Scope"), async () => {
			await frappe.xcall("av_tools.selling_pricing_engine.dashboard.clear_dashboard_scope");
			frappe.msgprint(__("Your saved dashboard scope was reset."));
		});
	},
	filters: [
		{ fieldname: "branch", label: __("Pricing Branch"), fieldtype: "Link", options: "Branch" },
		{
			fieldname: "supplier",
			label: __("Cost Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
			description: __(
				"Required for catalogues above 500 Items; dashboard supports 5,000 SKUs per scope."
			),
		},
		{
			fieldname: "include_child_groups",
			label: __("Include Child Item Groups"),
			fieldtype: "Check",
		},
		{ fieldname: "brand", label: __("Brand"), fieldtype: "Link", options: "Brand" },
		{
			fieldname: "source_doctype",
			label: __("Cost Source Type"),
			fieldtype: "Select",
			options: "\nPurchase Invoice\nPurchase Receipt",
		},
		{
			fieldname: "source_document",
			label: __("Current Cost Source"),
			fieldtype: "Dynamic Link",
			options: "source_doctype",
		},

		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
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
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{
			fieldname: "as_on",
			label: __("Price Effective As On"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "chart_view",
			label: __("Chart View"),
			fieldtype: "Select",
			options:
				"Coverage\nRevision Pipeline\nReview Exceptions\nPublication Trend\nPolicy Coverage\nCost Sources",
			default: "Coverage",
		},
		{ fieldname: "metric", label: __("Metric"), fieldtype: "Data", hidden: 1 },
		{ fieldname: "chart_only", label: __("Chart Only"), fieldtype: "Check", hidden: 1 },
	],
};
