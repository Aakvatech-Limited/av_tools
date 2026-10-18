frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Generated Existing Assets"), () => {
			frappe.set_route("List", "Asset", { av_nta_purchase_invoice: frm.doc.name });
		}, __("View"));
	},
	async before_cancel(frm) {
		const response = await frappe.call({
			method: "av_tools.asset_reconciliation.asset_cleanup.preview_invoice_cleanup",
			args: { purchase_invoice: frm.doc.name },
		});
		const summary = response.message;
		if (!summary.assets.length) return;
		if (summary.blockers.length) {
			frappe.throw(summary.blockers.map((value) => frappe.utils.escape_html(value)).join("<br>"));
		}
		return new Promise((resolve, reject) => frappe.confirm(
			__("Cancelling this invoice will also attempt to cancel and delete {0} generated Assets and their owned schedules, movements and Asset-only depreciation journals. Continue?", [summary.assets.length]),
			resolve,
			() => { frappe.validated = false; reject(new Error(__("Cancellation stopped"))); }
		));
	},
});
