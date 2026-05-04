frappe.ui.form.on("Landed Cost Voucher", {
    validate(frm) {
        (frm.doc.items || []).forEach((d) => {
            if (!d.qty) return;
            const applicable_item = (d.applicable_charges || 0) / d.qty;
            const price_item = applicable_item + (d.amount || 0) / d.qty;
            frappe.model.set_value(
                d.doctype,
                d.name,
                "applicable_charges_per_item",
                applicable_item
            );
            frappe.model.set_value(
                d.doctype,
                d.name,
                "price_per_item",
                price_item
            );
        });
    },
    import_file(frm) {
        frm.clear_table("taxes");
        if (frm.doc.import_file) {
            frappe.call({
                method: "av_tools.av_tools_hooks.landed_cost_voucher.get_landed_cost_expenses",
                args: {
                    import_file: frm.doc.import_file,
                },
                async: false,
                callback(r) {
                    if (r.message) {
                        r.message.forEach((element) => {
                            const child = frm.add_child("taxes");
                            frappe.model.set_value(
                                child.doctype,
                                child.name,
                                "expense_account",
                                element.expense_account
                            );
                            frappe.model.set_value(
                                child.doctype,
                                child.name,
                                "description",
                                element.description
                            );
                            frappe.model.set_value(
                                child.doctype,
                                child.name,
                                "amount",
                                element.amount
                            );
                        });
                    }
                },
            });
        }
        frm.refresh_field("taxes");
    },
});
