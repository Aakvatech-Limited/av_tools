// Copyright (c) 2023, Aakvatech and contributors
// For license information, please see license.txt

frappe.ui.form.on("OTP Register", {
	refresh: function (frm) {
		// set filter for on party_type field
		frm.set_query("party_type", function () {
			return {
				filters: {
					name: [
						"in",
						[
							"Customer",
							"Supplier",
							"Employee",
							"User",
							"Lead",
							"Student",
							"Guardian",
							"Instructor",
							"Member",
							"Sales Partner",
							"Sales Person",
							"Teacher",
							"Tenant",
							"Visitor",
							"Patient",
						],
					],
				},
			};
		});
		// if not Validate == 1 add custom button to validate OTP
		if (!frm.doc.registered && frm.doc.party_type && frm.doc.party && frm.doc.docstatus == 0) {
			frm.add_custom_button(__("Register OTP"), function () {
				// check if doc is not saved
				if (frm.is_dirty()) {
					frappe.show_alert({
						message: __("Please save the document first"),
						indicator: "red",
					});
					return;
				}
				frappe.call({
					method: "av_tools.authotp.doctype.otp_register.otp_register.register_otp",
					args: {
						otp_doc: frm.doc,
					},
					callback: function (r) {
						if (r.message) {
							show_popup_for_otp_validation(frm, r.message);
						}
					},
				});
			});
		}
	},
	party_type: function (frm) {
		// clear party, party_name and user_name fields
		frm.set_value("party", "");
		frm.set_value("party_name", "");
		frm.set_value("user_name", "");
	},
});

function show_popup_for_otp_validation(frm, qr_code_link) {
	// show popup to dispaly QR code and validate OTP
	const fields = [
		{
			fieldtype: "Data",
			fieldname: "otp_code",
			label: __("OTP Code"),
			reqd: 1,
		},
		{
			fieldtype: "Button",
			fieldname: "validate_otp",
			label: __("Validate OTP"),
			click: function () {
				// validate OTP
				validate_otp(frm, d);
			},
		},
	];
	if (qr_code_link) {
		// add field to show QR code image as first field
		fields.unshift({
			fieldtype: "HTML",
			fieldname: "qr_code",
			label: __("QR Code"),
			options: `<img src="${qr_code_link}" style="width: 100%; height: 100%;"/>`,
		});
	}
	var d = new frappe.ui.Dialog({
		title: __("Validate OTP"),
		fields: fields,
	});
	d.show();
}

function validate_otp(frm, d) {
	// validate OTP
	frappe.call({
		method: "av_tools.authotp.doctype.otp_register.otp_register.validate_otp",
		args: {
			otp_doc: frm.doc,
			otp_code: d.get_value("otp_code"),
			submit: true,
		},
		callback: function (r) {
			if (r.message) {
				frm.reload_doc();
				// close popup
				d.hide();
			}
		},
	});
}
