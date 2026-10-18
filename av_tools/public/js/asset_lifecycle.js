frappe.ui.form.on("Asset", {
	refresh(frm) {
		if (frm.is_new() || !frm.perm.some((permission) => permission.delete)) return;
		frm.add_custom_button(__("Cancel and Delete Asset"), async () => {
			const response = await frappe.call({
				method: "av_tools.asset_reconciliation.asset_cleanup.preview_asset_cleanup",
				args: { asset: frm.doc.name },
				freeze: true,
			});
			const plan = response.message;
			const esc = (value) => frappe.utils.escape_html(String(value || ""));
			if (plan.blockers.length) {
				frappe.msgprint({
					title: __("Asset cleanup blocked"),
					message: plan.blockers.map(esc).join("<br>"),
					indicator: "orange",
				});
				return;
			}
			const rows = plan.records.map((record) =>
				`<li>${esc(record.doctype)}: ${esc(record.name)} — ${record.docstatus === 1 ? __("Cancel, then delete") : __("Delete")}</li>`
			).join("");
			const dialog = new frappe.ui.Dialog({
				title: __("Review Asset cancellation and deletion"),
				size: "large",
				fields: [
					{ fieldtype: "HTML", fieldname: "records", options:
						`<p>${__("The following records will be deleted. Submitted records will be cancelled first.")}</p><ul>${rows}</ul>` +
						`<p>${__("Asset-only depreciation journals are included. Purchase documents and shared records are not deleted.")}</p>` +
						`<p>${__("Related ledger cleanup follows Accounts Settings and ERPNext deletion rules.")}</p>` +
						`<p>${__("Activity created by cancellation is also cleaned up; ERPNext retains its normal deletion audit trail.")}</p>` },
					{ fieldtype: "Check", fieldname: "confirmed", label: __("I confirm cancellation and deletion of the listed Asset and its owned links"), reqd: 1 },
				],
				primary_action_label: __("Cancel and Delete"),
				async primary_action(values) {
					if (!values.confirmed) return;
					await frappe.call({
						method: "av_tools.asset_reconciliation.asset_cleanup.cancel_and_delete_asset",
						args: { asset: frm.doc.name, token: plan.token, confirm: 1 },
						freeze: true,
						freeze_message: __("Cancelling and deleting Asset links…"),
					});
					dialog.hide();
					frappe.show_alert({ message: __("Asset and owned links deleted"), indicator: "green" });
					frappe.set_route("List", "Asset");
				},
			});
			dialog.show();
		}, __("Actions"));
	},
});
