// Copyright (c) 2023, Aakvatech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Invoice", {
	refresh: function (frm) {
		// add custom button to validate OTP
		if (frm.doc.docstatus == 0 && !frm.doc.authotp_validated) {
			frm.add_custom_button(__("Validate OTP"), function () {
				// check if doc is not saved
				if (frm.is_dirty()) {
					frappe.show_alert({
						message: __("Please save the document first"),
						indicator: "red",
					});
					return;
				}
				// show popup to validate OTP
				show_popup_for_otp_validation(frm);
			});
		}
		frm.set_query("authotp_method", function () {
			return {
				filters: {
					party_type: "Customer",
					party: frm.doc.customer,
					docstatus: 1,
				},
			};
		});
	},
	customer: function (frm) {
		// clear authotp_method and authotp_validated fields on customer change
		frm.set_value("authotp_validated", 0);
	},
});

function show_popup_for_otp_validation(frm) {
	// show popup to dispaly QR code and validate OTP
	const fields = [
		{
			fieldtype: "Data",
			fieldname: "otp_code",
			label: __("OTP Code"),
			reqd: 1,
		},
	];
	const d = new frappe.ui.Dialog({
		title: __("Validate OTP"),
		fields: fields,
	});
	d.set_primary_action(__("Validate OTP"), function () {
		if (!frm.doc.authotp_method) {
			frappe.show_alert({
				message: __("Please set AuthOTP Method in the document"),
				indicator: "red",
			});
			return;
		}
		const otp_code = d.get_value("otp_code");
		if (otp_code) {
			frappe.call({
				method: "av_tools.authotp.doctype.otp_register.otp_register.validate_doc_otp",
				args: {
					otp_register_name: frm.doc.authotp_method,
					otp_code: otp_code,
				},
				callback: function (r) {
					if (r.message) {
						frappe.show_alert({
							message: __("OTP Validated Successfully"),
							indicator: "green",
						});
						frm.set_value("authotp_validated", 1);
						d.hide();
						frm.save();
						// frm.reload_doc();
					}
				},
			});
		}
	});
	d.show();
}
