// Copyright (c) 2026, Aakvatech and contributors
// For license information, please see license.txt

frappe.provide("av_tools.financial_drilldown_ledger");

av_tools.financial_drilldown_ledger.open_voucher = function (voucher_type, voucher_no) {
	if (!voucher_type || !voucher_no) return;
	frappe.set_route("Form", voucher_type, voucher_no);
};

frappe.query_reports["Financial Drilldown Ledger"] = {
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
			fieldname: "finance_book",
			label: __("Finance Book"),
			fieldtype: "Link",
			options: "Finance Book",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "MultiSelectList",
			options: "Account",
			reqd: 1,
			get_data: (txt) =>
				frappe.db.get_link_options("Account", txt, {
					company: frappe.query_report.get_filter_value("company"),
				}),
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Autocomplete",
			options: Object.keys(frappe.boot.party_account_types),
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "MultiSelectList",
			options: "party_type",
			depends_on: "party_type",
			get_data: function (txt) {
				const party_type = frappe.query_report.get_filter_value("party_type");
				if (!party_type) return [];
				return frappe.db.get_link_options(party_type, txt);
			},
		},
		{
			fieldname: "presentation_currency",
			label: __("Currency"),
			fieldtype: "Select",
			options: erpnext.get_presentation_currency_list(),
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "MultiSelectList",
			options: "Cost Center",
			get_data: (txt) =>
				frappe.db.get_link_options("Cost Center", txt, {
					company: frappe.query_report.get_filter_value("company"),
				}),
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "MultiSelectList",
			options: "Project",
			get_data: (txt) =>
				frappe.db.get_link_options("Project", txt, {
					company: frappe.query_report.get_filter_value("company"),
				}),
		},
		{
			fieldname: "include_dimensions",
			label: __("Consider Accounting Dimensions"),
			fieldtype: "Check",
			default: frappe.boot.sysdefaults.disable_include_dimensions ? 0 : 1,
		},
		{
			fieldname: "include_default_book_entries",
			label: __("Include Default FB Entries"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "provider",
			fieldtype: "Data",
			hidden: 1,
		},
		{
			fieldname: "master_type",
			fieldtype: "Data",
			hidden: 1,
		},
		{
			fieldname: "master_value",
			fieldtype: "Data",
			hidden: 1,
		},
		{
			fieldname: "warehouse",
			fieldtype: "Link",
			options: "Warehouse",
			hidden: 1,
		},
		{
			fieldname: "item_group",
			fieldtype: "Link",
			options: "Item Group",
			hidden: 1,
		},
		{
			fieldname: "item",
			fieldtype: "Link",
			options: "Item",
			hidden: 1,
		},
		{
			fieldname: "asset_category",
			fieldtype: "Link",
			options: "Asset Category",
			hidden: 1,
		},
		{
			fieldname: "asset",
			fieldtype: "Link",
			options: "Asset",
			hidden: 1,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		if (column.fieldname === "voucher_no") {
			delete column.link_onclick;
			if (data && data.voucher_type && data.voucher_no) {
				column.link_onclick =
					"av_tools.financial_drilldown_ledger.open_voucher(" +
					JSON.stringify(data.voucher_type) +
					", " +
					JSON.stringify(data.voucher_no) +
					")";
			}
		}
		return default_formatter(value, row, column, data);
	},
};

erpnext.utils.add_dimensions("Financial Drilldown Ledger", 9);
