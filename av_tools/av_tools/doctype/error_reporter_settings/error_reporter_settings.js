frappe.ui.form.on("Error Reporter Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Generate Site Identity"), () => {
			frappe.call({
				method: "av_tools.av_tools.doctype.error_reporter_settings.error_reporter_settings.generate_identity",
				freeze: true,
				callback() {
					frm.reload_doc();
				},
			});
		});

		frm.add_custom_button(__("Enroll with Central Registry"), () => {
			frappe.call({
				method: "av_tools.av_tools.doctype.error_reporter_settings.error_reporter_settings.enroll_now",
				freeze: true,
				callback(r) {
					frm.reload_doc();
					if (r.message) frappe.msgprint(JSON.stringify(r.message, null, 2));
				},
			});
		});

		frm.add_custom_button(__("Send Yesterday's Errors"), () => {
			frappe.call({
				method: "av_tools.error_reporting.reporter.send_yesterday_now",
				freeze: true,
				callback(r) {
					frm.reload_doc();
					if (r.message) frappe.msgprint(JSON.stringify(r.message, null, 2));
				},
			});
		});
	},
});
