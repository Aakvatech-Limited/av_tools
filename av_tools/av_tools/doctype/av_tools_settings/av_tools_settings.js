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
		});
	},
});
