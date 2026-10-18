frappe.query_reports["Fixed Asset Financial Reconciliation"] = {
	filters: [
		{
			fieldname: "company",
			label: "Company",
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "as_on",
			label: "As On",
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "view_mode",
			label: "View",
			fieldtype: "Select",
			options: ["All Records", "Exceptions Only"],
			default: "Exceptions Only",
			reqd: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const formatted = default_formatter(value, row, column, data);
		if (column.fieldname === "reconciliation" && data && data.reconciliation) {
			const id = String(data.reconciliation);
			const url = "/app/asset-capitalization-reconciliation/" + encodeURIComponent(id);
			const safeLabel = frappe.utils.escape_html
				? frappe.utils.escape_html(id)
				: id.replace(/[&<>"']/g, "");
			return (
				'<a href="' +
				url +
				'" title="Open Asset Capitalization Reconciliation" ' +
				'style="display:inline-block;padding:3px 9px;border-radius:6px;' +
				"background:var(--control-bg, var(--subtle-fg, #374151));" +
				"color:var(--text-color, #ffffff) !important;" +
				"border:1px solid var(--primary, #60a5fa);" +
				"font-weight:700;text-decoration:underline;text-underline-offset:3px;" +
				'white-space:nowrap;">↗ ' +
				safeLabel +
				"</a>"
			);
		}
		return formatted;
	},
};
