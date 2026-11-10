["Sales Invoice", "Purchase Invoice"].forEach(doctype => {
    frappe.ui.form.on(doctype, {
        refresh(frm) {
            if (frm.is_new() || frm.doc.docstatus !== 1) return;
            if (!(frappe.user_roles || []).some(role => ["Accounts Manager", "System Manager"].includes(role))) return;
            frm.add_custom_button("Redo Item-wise Tax Detail", () => {
                frappe.new_doc("Item Wise Tax Detail Rebuild", {
                    company: frm.doc.company,
                    source_doctype: frm.doc.doctype,
                    source_invoice: frm.doc.name,
                    from_date: frm.doc.posting_date,
                    to_date: frm.doc.posting_date
                });
            }, "Tools");
        }
    });
});
