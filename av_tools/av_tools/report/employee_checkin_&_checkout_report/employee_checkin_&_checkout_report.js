// Copyright (c) 2016, Aakvatech and contributors
// For license information, please see license.txt
/* eslint-disable */

(function () {
	const REPORT_NAME = "Employee Checkin & Checkout Report";
	const SUMMARY_SELECTOR = "#employee-checkin-summary";

	function remove_checkin_summary() {
		$(SUMMARY_SELECTOR).remove();
	}

	function render_checkin_summary(report, summary) {
		remove_checkin_summary();

		if (!report || !report.page || !report.page.wrapper || !summary) {
			return;
		}

		let summary_html = `
			<div id="employee-checkin-summary" style="display: flex; gap: 16px; justify-content: center; margin-bottom: 16px;">
				<div class="card text-white bg-success mb-3" style="max-width: 18rem;">
					<div class="card-header">IN</div>
					<div class="card-body">
						<h5 class="card-title">${summary.in_count}</h5>
						<p class="card-text">Checkins for <b>${summary.date}</b></p>
					</div>
				</div>
				<div class="card text-white bg-danger mb-3" style="max-width: 18rem;">
					<div class="card-header">OUT</div>
					<div class="card-body">
						<h5 class="card-title">${summary.out_count}</h5>
						<p class="card-text">Checkouts for <b>${summary.date}</b></p>
					</div>
				</div>
			</div>
		`;

		const $wrapper = $(report.page.wrapper);
		const $page_form = $wrapper.find(".page-form").first();
		const $summary = $(summary_html);

		if ($page_form.length) {
			$summary.insertBefore($page_form);
		} else {
			const $page_body = $wrapper.find(".page-body").first();
			const $target = $page_body.length
				? $page_body
				: $(report.page.main || report.page.wrapper);
			$target.prepend($summary);
		}
	}

	if (!frappe.__employee_checkin_checkout_report_cleanup) {
		frappe.router.on("change", function () {
			const route = frappe.get_route();
			const is_checkin_report =
				route && route[0] === "query-report" && route[1] === REPORT_NAME;

			if (!is_checkin_report) {
				remove_checkin_summary();
			}
		});

		frappe.__employee_checkin_checkout_report_cleanup = true;
	}

	frappe.query_reports[REPORT_NAME] = {
		filters: [
			{
				fieldname: "from_date",
				label: __("From Date"),
				fieldtype: "Date",
				width: "150px",
				reqd: 1,
			},
			{
				fieldname: "to_date",
				label: __("To Date"),
				fieldtype: "Date",
				width: "150px",
				reqd: 1,
			},
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				width: "150px",
				reqd: 1,
			},
			{
				fieldname: "department",
				label: __("Department"),
				fieldtype: "Link",
				options: "Department",
				default: "",
				width: "150px",
				reqd: 0,
				get_query: function () {
					var company = frappe.query_report.get_filter_value("company");
					return {
						doctype: "Department",
						filters: {
							company: company,
						},
					};
				},
			},
			{
				fieldname: "employee",
				label: __("Employee"),
				fieldtype: "Link",
				options: "Employee",
				width: "150px",
				reqd: 0,
			},
		],
		onload: function (report) {
			frappe.call({
				method: "av_tools.av_tools.report.employee_checkin_&_checkout_report.employee_checkin_&_checkout_report.get_employee_checkin_summary",
				callback: function (r) {
					render_checkin_summary(report, r.message);
				},
			});
		},
	};
})();
