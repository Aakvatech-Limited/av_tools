// Copyright (c) 2024, Aakvatech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Delivery Exchange Item", {
	refresh: (frm) => {
		frm.set_query("item_exchange", "stock_items", function () {
			var data = {
				filters: {
					is_stock_item: 1,
				},
			};
			return data;
		});
		frm.set_query("item_exchange", "non_stock_items", function () {
			var data = {
				filters: {
					is_stock_item: 0,
				},
			};
			return data;
		});
	},

	ref_docname: (frm) => {
		if (frm.doc.ref_docname) {
			fetch_item_details(frm);
		}
	},
});

function fetch_item_details(frm) {
	frappe.call({
		method: "av_tools.av_tools.doctype.delivery_exchange_item.delivery_exchange_item.get_item_details",
		args: {
			doctype: frm.doc.ref_doctype,
			doctype_id: frm.doc.ref_docname,
			packed: false,
			// 'item_code': row.item_sold_or_delivered,
		},
		callback: function (r) {
			if (!r.exc) {
				console.log(r.message);
				frm.doc.stock_items = [];
				frm.doc.non_stock_items = [];
				frm.refresh_field("stock_items");
				frm.refresh_field("non_stock_items");
				for (let d of r.message) {
					if (d.is_stock_item) {
						let row = frm.add_child("stock_items", {
							item_sold_or_delivered: d.item_code,
							amount_exchange: d.amount,
							warehouse: d.warehouse,
							qty_sold_or_delivered: d.qty,
							rate_sold_or_delivered: d.rate,
							uom: d.uom,
							amount_sold_or_delivered: d.amount,
						});
					} else {
						let row = frm.add_child("non_stock_items", {
							item_sold_or_delivered: d.item_code,
							amount_exchange: d.amount,
							warehouse: d.warehouse,
							qty_sold_or_delivered: d.qty,
							rate_sold_or_delivered: d.rate,
							uom: d.uom,
							amount_sold_or_delivered: d.amount,
						});
					}

					frm.refresh_field("stock_items");
					frm.refresh_field("non_stock_items");
				}
			}
		},
	});
}
