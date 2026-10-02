// Copyright (c) 2026, Aakvatech and contributors
// For license information, please see license.txt

frappe.provide("av_tools.financial_master_summary");

av_tools.financial_master_summary.open_party_ledger = function (data) {
	if (!data || !data.party_type || !data.party) return;

	const get = (fieldname) => frappe.query_report.get_filter_value(fieldname, false);
	frappe.route_options = {
		company: get("company"),
		from_date: get("from_date"),
		to_date: get("to_date"),
		account: get("account"),
		party_type: data.party_type,
		party: data.party,
		categorize_by: "Categorize by Voucher (Consolidated)",
	};

	frappe.query_report.filters.forEach(function (filter) {
		if (!filter.df || !filter.df.fieldname) return;
		const fieldname = filter.df.fieldname;
		if (fieldname in frappe.route_options) return;

		const value = filter.get_value();
		if (value !== undefined && value !== null && value !== "" && !(Array.isArray(value) && !value.length)) {
			frappe.route_options[fieldname] = value;
		}
	});

	frappe.set_route("query-report", "General Ledger");
};

frappe.query_reports["Financial Master Summary"] = {
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
			fieldname: "account",
			label: __("Account"),
			fieldtype: "Link",
			options: "Account",
			reqd: 1,
			get_query: () => ({
				filters: {
					company: frappe.query_report.get_filter_value("company"),
					is_group: 0,
				},
			}),
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
			fieldname: "finance_book",
			label: __("Finance Book"),
			fieldtype: "Link",
			options: "Finance Book",
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
			fieldname: "ageing_based_on",
			label: __("Ageing Based On"),
			fieldtype: "Select",
			options: "Posting Date\nDue Date",
			default: "Posting Date",
		},
		{
			fieldname: "age_as_on",
			label: __("Age as on"),
			fieldtype: "Select",
			options: "Report Date\nToday",
			default: "Report Date",
		},
		{
			fieldname: "range",
			label: __("Ageing Range"),
			fieldtype: "Data",
			default: "30, 60, 90, 120",
		},
		{
			fieldname: "show_future_payments",
			label: __("Show Future Payments"),
			fieldtype: "Check",
		},
		{
			fieldname: "show_gl_balance",
			label: __("Show GL Balance"),
			fieldtype: "Check",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		if (data && column.fieldname === "party" && data.party_type && data.party) {
			column.link_onclick =
				"av_tools.financial_master_summary.open_party_ledger(" +
				JSON.stringify({ party_type: data.party_type, party: data.party }) +
				")";
		}
		return default_formatter(value, row, column, data);
	},
};

erpnext.utils.add_dimensions("Financial Master Summary", 7);
