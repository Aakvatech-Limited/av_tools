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

	after_save(frm) {
		if (!frappe.boot) {
			return;
		}

		frappe.boot.av_tools_capture_settings = {
			enabled: Boolean(frm.doc.enable_camera_capture_override),
			force_web_capture_on_mobile: Boolean(frm.doc.force_web_capture_on_mobile),
			ideal_width: cint(frm.doc.camera_capture_ideal_width) || 1920,
			ideal_height: cint(frm.doc.camera_capture_ideal_height) || 1080,
			min_width: cint(frm.doc.camera_capture_min_width) || 0,
			min_height: cint(frm.doc.camera_capture_min_height) || 0,
		};
	},
});
