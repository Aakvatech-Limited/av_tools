frappe.ui.form.on("Stock Entry", {
	onload(frm) {
		if (frm.doc.docstatus !== 0) {
			return;
		}

		frm.set_query("repack_template", function () {
			return {
				filters: {
					docstatus: 1,
				},
			};
		});
	},
	repack_template(frm) {
		frm.trigger("get_repack_template");
	},
	repack_qty(frm) {
		frm.trigger("get_repack_template");
	},
	get_repack_template(frm) {
		if (!frm.doc.repack_template || !frm.doc.repack_qty) {
			return;
		}

		frappe.call({
			method: "av_tools.av_tools_hooks.repack_template.get_repack_template",
			args: {
				template_name: frm.doc.repack_template,
				qty: frm.doc.repack_qty,
			},
			callback(r) {
				frm.clear_table("items");
				(r.message || []).forEach((d) => {
					const child = frm.add_child("items");
					frappe.model.set_value(child.doctype, child.name, "item_code", d.item_code);
					frappe.model.set_value(child.doctype, child.name, "qty", d.qty);
					frappe.model.set_value(child.doctype, child.name, "uom", d.item_uom);
					if (d.s_warehouse) {
						frappe.model.set_value(child.doctype, child.name, "s_warehouse", d.s_warehouse);
					}
					if (d.t_warehouse) {
						frappe.model.set_value(child.doctype, child.name, "t_warehouse", d.t_warehouse);
					}
				});
				frm.refresh_field("items");
			},
		});
	},
	stock_entry_type(frm) {
		if (frm.doc.stock_entry_type === "Repack from template") {
			frappe.meta.get_docfield("Stock Entry Detail", "item_code", frm.doc.name).read_only = 1;
			frappe.meta.get_docfield("Stock Entry Detail", "item_group", frm.doc.name).read_only = 1;
			$(".grid-add-multiple-rows").hide();
			$(".grid-add-row").hide();
			$(".grid-remove-rows").hide();
			$(".grid-download").hide();
			$(".grid-upload").hide();
			frm.toggle_reqd("qty", 1);
		} else {
			frappe.meta.get_docfield("Stock Entry Detail", "item_code", frm.doc.name).read_only = 0;
			frappe.meta.get_docfield("Stock Entry Detail", "item_group", frm.doc.name).read_only = 0;
			$(".grid-add-multiple-rows").show();
			$(".grid-add-row").show();
			$(".grid-remove-rows").show();
			$(".grid-download").show();
			$(".grid-upload").show();
			frm.toggle_reqd("qty", 0);
		}
		frm.refresh_field("items");
	},
});
