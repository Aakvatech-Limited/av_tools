// Copyright (c) 2021, Aakvatech and contributors
// For license information, please see license.txt

frappe.ui.form.on("AV Tools Settings", {
	setup(frm) {
		frm.set_query("approval_doctype", () => {
			return {
				filters: {
					istable: 0,
					issingle: 0,
				},
			};
		,
	enable_full_access_role(frm) {
		if (!frm.doc.enable_full_access_role || frm.__full_access_consent_accepted) {
			return;
		}

		frm.set_value("enable_full_access_role", 0);

		const dialog = new frappe.ui.Dialog({
			title: __("FULL ACCESS Authorization"),
			fields: [
				{
					fieldtype: "HTML",
					options: `
						<div class="alert alert-danger">
							<strong>${__("Privileged access warning")}</strong><br><br>
							${__(
								"FULL ACCESS grants broad access to all eligible non-Frappe DocTypes, Reports, Pages and Workspaces."
							)}
							<br><br>
							${__(
								"Only the authorized Lead Implementor, signed in as Administrator, may enable this setting."
							)}
							<br><br>
							${__(
								"By clicking I Accept, you confirm that you understand the impact and authorize AV Tools to apply and continuously maintain this access policy. Your consent will be written to Activity Log."
							)}
						</div>
					`,
				},
			],
			primary_action_label: __("I Accept"),
			primary_action() {
				frappe.call({
					method: "av_tools.av_tools.doctype.av_tools_settings.av_tools_settings.accept_full_access_consent",
					freeze: true,
					callback(r) {
						if (!r.exc && r.message && r.message.accepted) {
							frm.__full_access_consent_accepted = true;
							dialog.hide();
							frm.set_value("enable_full_access_role", 1);
						}
					},
				});
			},
			secondary_action_label: __("Cancel"),
			secondary_action() {
				dialog.hide();
			},
		});

		dialog.show();
	},
});	},
});
