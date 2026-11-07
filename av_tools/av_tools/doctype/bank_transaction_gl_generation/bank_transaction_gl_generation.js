frappe.ui.form.on("Bank Transaction GL Generation", {
    setup: function (frm) {
        frm.set_query("bank_account", function () {
            return {filters: {company: frm.doc.company, is_company_account: 1}};
        });
    },
    company: function (frm) { frm.set_value("bank_account", ""); },
    refresh: function (frm) {
        if (frm.gl_refresh_timer) clearTimeout(frm.gl_refresh_timer);
        if (frm.is_new()) return;
        frm.disable_save();
        frm.add_custom_button("View Generated Drafts", function () {
            frappe.set_route("List", "Bank Transaction", {custom_gl_generation_run: frm.doc.name, docstatus: 0});
        });
        const mode = frm.doc.dry_run ? "Preview" : "Generation";
        const text = mode + ": " + frm.doc.status + " | Checked: " + (frm.doc.scanned_count || 0) +
            " | Eligible: " + (frm.doc.eligible_count || 0) + " | Created: " + (frm.doc.created_count || 0) +
            " | Skipped: " + (frm.doc.skipped_count || 0) + " | Errors: " + (frm.doc.failed_count || 0);
        frm.dashboard.set_headline_alert(text);
        if (["Queued", "Running"].includes(frm.doc.status)) {
            frm.gl_refresh_timer = setTimeout(function () {
                if (cur_frm === frm && !frm.is_dirty()) frm.reload_doc();
            }, 3000);
        }
    }
});
