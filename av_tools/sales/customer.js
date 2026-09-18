frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Customer Statement"), function () {
			frappe.route_options = {
				customer: frm.doc.name,
			};

			frappe.set_route("customer-statement");
		});
	},
});
