$(document).on("app_ready", function () {
	if (!erpnext || !erpnext.financial_statements) return;

	const original_open_general_ledger = erpnext.financial_statements.open_general_ledger;

	erpnext.financial_statements.open_general_ledger = function (data) {
		if (!data.account && !data.accounts) return;

		function navigate_based_on_type(account_type) {
			if (account_type === "Receivable") {
				frappe.route_options = {
					company: frappe.query_report.get_filter_value("company"),
					report_date: data.to_date || data.year_end_date,
					ageing_based_on: "Posting Date",
				};
				frappe.set_route("query-report", "Accounts Receivable Summary");
			} else if (account_type === "Payable") {
				frappe.route_options = {
					company: frappe.query_report.get_filter_value("company"),
					report_date: data.to_date || data.year_end_date,
					ageing_based_on: "Posting Date",
				};
				frappe.set_route("query-report", "Accounts Payable Summary");
			} else {
				original_open_general_ledger(data);
			}
		}

		if (data.account_type) {
			navigate_based_on_type(data.account_type);
		} else {
			let account_name = data.account || data.accounts;
			frappe.db.get_value("Account", account_name, "account_type", function (r) {
				if (r && r.account_type) {
					navigate_based_on_type(r.account_type);
				} else {
					original_open_general_ledger(data);
				}
			});
		}
	};
});
