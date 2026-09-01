(function () {
	frappe.provide("av_tools.financial_statements");

	const ACCOUNTS_RECEIVABLE_SUMMARY = "Accounts Receivable Summary";
	const GENERAL_LEDGER = "General Ledger";
	const VOUCHER_CONSOLIDATED = "Categorize by Voucher (Consolidated)";

	function get_report_filter_value(fieldname) {
		return frappe.query_report ? frappe.query_report.get_filter_value(fieldname, false) : null;
	}

	function get_year_start(date_value) {
		const date = date_value || frappe.datetime.get_today();
		return `${date.slice(0, 4)}-01-01`;
	}

	function retry_installer(installer, interval_key) {
		if (installer() || av_tools.financial_statements[interval_key]) return;

		let attempts = 0;
		av_tools.financial_statements[interval_key] = setInterval(function () {
			attempts++;

			if (installer() || attempts > 50) {
				clearInterval(av_tools.financial_statements[interval_key]);
				av_tools.financial_statements[interval_key] = null;
			}
		}, 200);
	}

	av_tools.financial_statements.open_customer_general_ledger = function (data) {
		if (!data || data.party_type !== "Customer" || !data.party) return;

		const to_date = get_report_filter_value("report_date") || frappe.datetime.get_today();

		frappe.route_options = {
			company: get_report_filter_value("company"),
			from_date: get_year_start(to_date),
			to_date: to_date,
			party_type: "Customer",
			party: data.party,
			categorize_by: VOUCHER_CONSOLIDATED,
		};

		["finance_book", "cost_center", "project"].forEach(function (fieldname) {
			const value = get_report_filter_value(fieldname);
			if (value) {
				frappe.route_options[fieldname] = value;
			}
		});

		frappe.set_route("query-report", GENERAL_LEDGER);
	};

	function install_accounts_receivable_summary_override() {
		const report = frappe.query_reports && frappe.query_reports[ACCOUNTS_RECEIVABLE_SUMMARY];

		if (!report || report.__av_tools_customer_gl_override_installed) {
			return Boolean(report);
		}

		const original_formatter = report.formatter;

		report.formatter = function (value, row, column, data, default_formatter, filter) {
			if (column.fieldname === "party") {
				if (data && data.party_type === "Customer" && data.party) {
					column.link_onclick =
						"av_tools.financial_statements.open_customer_general_ledger(" +
						JSON.stringify({ party_type: data.party_type, party: data.party }) +
						")";
				} else {
					delete column.link_onclick;
				}
			}

			if (original_formatter) {
				return original_formatter.call(
					this,
					value,
					row,
					column,
					data,
					default_formatter,
					filter
				);
			}

			return default_formatter(value, row, column, data);
		};

		report.__av_tools_customer_gl_override_installed = true;
		return true;
	}

	function install_financial_statements_override() {
		if (typeof erpnext === "undefined" || !erpnext.financial_statements) {
			return false;
		}
		if (erpnext.financial_statements.__av_tools_override_installed) {
			return true;
		}

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
					frappe.set_route("query-report", ACCOUNTS_RECEIVABLE_SUMMARY);
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
				const account_name = data.account || data.accounts;
				frappe.db.get_value("Account", account_name, "account_type", function (r) {
					if (r && r.account_type) {
						navigate_based_on_type(r.account_type);
					} else {
						original_open_general_ledger(data);
					}
				});
			}
		};

		erpnext.financial_statements.__av_tools_override_installed = true;
		return true;
	}

	function retry_financial_statement_override() {
		retry_installer(
			install_financial_statements_override,
			"financial_statements_retry_interval"
		);
	}

	function retry_accounts_receivable_summary_override() {
		retry_installer(
			install_accounts_receivable_summary_override,
			"accounts_receivable_summary_retry_interval"
		);
	}

	function is_accounts_receivable_summary_route() {
		const route = frappe.get_route();
		return route && route[0] === "query-report" && route[1] === ACCOUNTS_RECEIVABLE_SUMMARY;
	}

	$(document).on("app_ready startup", retry_financial_statement_override);

	frappe.router.on("change", function () {
		if (is_accounts_receivable_summary_route()) {
			retry_accounts_receivable_summary_override();
		}
	});

	$(function () {
		retry_financial_statement_override();
		if (is_accounts_receivable_summary_route()) {
			retry_accounts_receivable_summary_override();
		}
	});
})();
