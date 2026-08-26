// Copyright (c) 2022, Aakvatech and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item Barcode Update Tool', {
	'item_code': function (frm, cdt, cdn) {
		var doc = locals[cdt][cdn];
		if (doc.item_code) {
			frappe.call({
				method: "frappe.client.get",
				args: {
					name: doc.item_code,
					doctype: "Item"
				},
				callback(r) {
					// console.log(r);
					if (r.message) {
						for (var row in r.message.barcodes) {
							var child = frm.add_child("barcodes");
							frappe.model.set_value(child.doctype, child.name, "barcode", r.message.barcodes[row].barcode);
							frappe.model.set_value(child.doctype, child.name, "barcode_type", r.message.barcodes[row].barcode_type);
							frappe.model.set_value(child.doctype, child.name, "uom", r.message.barcodes[row].uom);
							refresh_field("barcodes");
						}
					}
				}
			})
		}
	},
	refresh(frm) {
		$(".btn-primary").hide()
	},
	'scan_barcode': function (frm) {
		add_scanned_barcode(frm);
	},
	'update_barcodes': function (frm) {
		frappe.call({
			method: "av_tools.av_tools.doctype.item_barcode_update_tool.item_barcode_update_tool.update_barcodes",
			args: {
				doc: frm.doc
			},
			callback: function (r) {
				// frappe.msgprint(__("Barcodes updated successfully for Item " + frm.doc.item_name))
				return
			}
		});
	},
})

function add_scanned_barcode(frm) {
	var barcode = (frm.doc.scan_barcode || "").trim();

	if (!barcode) {
		return;
	}

	frm.set_value("scan_barcode", "");

	if (!frm.doc.item_code) {
		frappe.msgprint(__("Select an Item before scanning a barcode."));
		return;
	}

	var exists = (frm.doc.barcodes || []).some(function(row) {
		return row.barcode === barcode;
	});

	if (exists) {
		frappe.show_alert({ message: __("Barcode already added."), indicator: "orange" });
		return;
	}

	var child = frm.add_child("barcodes");
	frappe.model.set_value(child.doctype, child.name, "barcode", barcode);

	if (frm.doc.default_unit_of_measure) {
		frappe.model.set_value(child.doctype, child.name, "uom", frm.doc.default_unit_of_measure);
	}

	refresh_field("barcodes");
}
