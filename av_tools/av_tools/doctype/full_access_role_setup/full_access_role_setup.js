frappe.ui.form.on("Full Access Role Setup", {
	enable_full_access_role(frm) {
		if (!frm.doc.enable_full_access_role || frm.__full_access_consent_accepted) {
			return;
		}

		if (frm.is_new()) {
			frm.set_value("enable_full_access_role", 0);
			frappe.msgprint(__("Save the company setup first, then enable FULL ACCESS."));
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
							<strong>${__("Privileged site-wide access warning")}</strong><br><br>
							${__("This setup is recorded against Company {0}, but the FULL ACCESS role is site-wide.", [
								frm.doc.company,
							])}
							<br><br>
							${__(
								"Enabling it grants broad access to eligible non-Frappe DocTypes, Reports, Pages and Workspaces. Only the authorized Lead Implementor using Administrator may proceed."
							)}
							<br><br>
							${__("Your acceptance will be written to Activity Log.")}
						</div>
					`,
				},
			],
			primary_action_label: __("I Accept"),
			primary_action() {
				frappe.call({
					method: "av_tools.av_tools.doctype.full_access_role_setup.full_access_role_setup.accept_full_access_consent",
					args: { setup_name: frm.doc.name },
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
});
