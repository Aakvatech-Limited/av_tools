frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Customer Statement"), function () {
			const url = frappe.urllib.get_full_url(
				"/app/customer-statement?customer=" + encodeURIComponent(frm.doc.name)
			);

			window.location.href = url;
		});
	},
});
