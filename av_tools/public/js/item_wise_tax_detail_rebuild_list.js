["Sales Invoice", "Purchase Invoice"].forEach(doctype => {
    const settings = frappe.listview_settings[doctype] || {};
    if (settings.av_tools_tax_rebuild_hook) return;
    const previous = settings.onload;
    frappe.listview_settings[doctype] = {
        ...settings,
        av_tools_tax_rebuild_hook: true,
        onload(listview) {
            if (previous) previous.call(this, listview);
            if (!(frappe.user_roles || []).some(role => ["Accounts Manager", "System Manager"].includes(role))) return;
            listview.page.add_inner_button("Redo Item-wise Tax Detail", () => {
                frappe.new_doc("Item Wise Tax Detail Rebuild", {
                    source_doctype: doctype,
                    company: frappe.defaults.get_user_default("Company"),
                    from_date: frappe.datetime.month_start(),
                    to_date: frappe.datetime.month_end()
                });
            });
        }
    };
});
