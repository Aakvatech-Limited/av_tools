// Copyright (c) 2026, Aakvatech and contributors
// For license information, please see license.txt

frappe.ui.form.on("License Register", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Create Renewal Task"), () => {
				frappe.new_doc("Task", {
					subject: `Renew License: ${frm.doc.license_name || frm.doc.name}`,
					exp_end_date: frm.doc.expiry_date,
					description: `Renewal task for License Register ${frm.doc.name}`,
				});
			});
		}
	},
});
