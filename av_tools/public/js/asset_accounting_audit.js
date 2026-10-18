frappe.ui.form.on("Asset", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			"Accounting Audit",
			async () => {
				const button = frm.custom_buttons && frm.custom_buttons["Accounting Audit"];
				if (button) button.prop("disabled", true);
				try {
					const response = await frappe.call({
						method: "av_tools.asset_reconciliation.api.asset_accounting_audit",
						args: { asset: frm.doc.name },
						freeze: true,
						freeze_message: "Loading Asset accounting entries...",
					});
					const result = response.message || {};
					const entries = result.entries || [];
					const esc = (value) =>
						frappe.utils.escape_html(String(value == null ? "" : value));
					const fmt = (value) =>
						format_currency(
							flt(value),
							result.currency || frappe.boot.sysdefaults.currency
						);
					const totals = {};
					entries.forEach((entry) => {
						const account = entry.account || "Unknown";
						if (!totals[account]) totals[account] = { debit: 0, credit: 0 };
						totals[account].debit += flt(entry.debit);
						totals[account].credit += flt(entry.credit);
					});
					const summary = Object.keys(totals)
						.sort()
						.map((account) => {
							const v = totals[account];
							return (
								"<tr><td>" +
								esc(account) +
								"</td><td class='text-right'>" +
								fmt(v.debit) +
								"</td><td class='text-right'>" +
								fmt(v.credit) +
								"</td><td class='text-right'>" +
								fmt(v.debit - v.credit) +
								"</td></tr>"
							);
						})
						.join("");
					const details = entries
						.map((entry) => {
							const type = entry.voucher_type || "";
							const url =
								"/app/" +
								frappe.router.slug(type) +
								"/" +
								encodeURIComponent(entry.voucher_no || "");
							return (
								"<tr><td>" +
								esc(entry.posting_date) +
								"</td><td><a href='" +
								esc(url) +
								"' target='_blank' rel='noopener noreferrer'>" +
								esc(entry.voucher_no) +
								"</a></td><td>" +
								esc(entry.account) +
								"</td><td class='text-right'>" +
								fmt(entry.debit) +
								"</td><td class='text-right'>" +
								fmt(entry.credit) +
								"</td></tr>"
							);
						})
						.join("");
					const tableClass = "table table-bordered table-condensed";
					const html =
						"<div style='max-height:65vh;overflow:auto'>" +
						"<p><strong>Asset:</strong> " +
						esc(result.asset_name) +
						" (" +
						esc(result.asset) +
						") &nbsp; <strong>Status:</strong> " +
						esc(result.status) +
						"</p>" +
						"<p><strong>Original cost:</strong> " +
						fmt(result.cost) +
						" &nbsp; <strong>Header book value:</strong> " +
						fmt(result.header_book_value) +
						" &nbsp; <strong>Scrap JE:</strong> " +
						esc(result.scrap_journal || "-") +
						"</p>" +
						"<h5>Accounting impact by account</h5><table class='" +
						tableClass +
						"'><thead><tr><th>Account</th><th>Debit</th><th>Credit</th><th>Net debit</th></tr></thead><tbody>" +
						(summary ||
							"<tr><td colspan='4'>No direct Asset GL references found.</td></tr>") +
						"</tbody></table><h5>Posted GL transactions (" +
						entries.length +
						")</h5>" +
						"<table class='" +
						tableClass +
						"'><thead><tr><th>Date</th><th>Journal / Voucher</th><th>Account</th><th>Debit</th><th>Credit</th></tr></thead><tbody>" +
						(details || "<tr><td colspan='5'>No entries found.</td></tr>") +
						"</tbody></table><p><strong>Total debit:</strong> " +
						fmt(result.total_debit) +
						" &nbsp; <strong>Total credit:</strong> " +
						fmt(result.total_credit) +
						"</p>" +
						(result.truncated
							? "<p class='text-warning'>Limited to 500 GL entries.</p>"
							: "") +
						"<p class='text-muted'>Read-only audit of GL Entries directly referencing this Asset. Shared or unlinked acquisition vouchers may require separate verification.</p></div>";
					const dialog = new frappe.ui.Dialog({
						title: "Asset Accounting Audit — " + frm.doc.name,
						size: "extra-large",
						fields: [{ fieldtype: "HTML", fieldname: "audit_html" }],
					});
					dialog.fields_dict.audit_html.$wrapper.html(html);
					dialog.show();
				} catch (error) {
					frappe.msgprint(
						"Unable to load Asset audit. Verify permission to read GL Entries and the audit API."
					);
				} finally {
					if (button) button.prop("disabled", false);
				}
			},
			"Audit"
		);
	},
});
