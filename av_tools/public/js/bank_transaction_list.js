(function () {
    const settings = frappe.listview_settings["Bank Transaction"] || {};
    const previous_onload = settings.onload;
    settings.onload = function (listview) {
        if (previous_onload) previous_onload.call(this, listview);
        const roles = frappe.user_roles || [];
        if (!roles.some(role => ["System Manager", "Accounts Manager", "Accounts User"].includes(role))) return;
        listview.page.add_inner_button("Generate from GL Entries", function () {
            const dialog = new frappe.ui.Dialog({
                title: "Generate Bank Transactions from GL",
                fields: [
                    {fieldname: "company", label: "Company", fieldtype: "Link", options: "Company", reqd: 1,
                        default: frappe.defaults.get_user_default("Company"),
                        onchange: function () { dialog.set_value("bank_account", ""); }},
                    {fieldname: "bank_account", label: "Bank Account", fieldtype: "Link", options: "Bank Account",
                        description: "Leave blank for all accessible company bank accounts.",
                        get_query: function () { return {filters: {company: dialog.get_value("company"), is_company_account: 1}}; }},
                    {fieldname: "from_date", label: "From Date", fieldtype: "Date",
                        description: "Optional. Leave blank to check all earlier GL entries."},
                    {fieldname: "cutoff_date", label: "Cut-off Date (inclusive)", fieldtype: "Date", reqd: 1,
                        default: frappe.datetime.get_today()},
                    {fieldname: "dry_run", label: "Preview Only", fieldtype: "Check", default: 1,
                        description: "Check eligibility and duplicates without creating Bank Transactions."},
                    {fieldtype: "HTML", options: "<p>Each GL row becomes a separate draft. Existing source GL links and voucher allocations are checked. Generated drafts have their source voucher linked; clearance occurs only on submission.</p>"}
                ],
                primary_action_label: "Start Background Job",
                primary_action: function (values) {
                    if (values.from_date && values.from_date > values.cutoff_date) {
                        frappe.throw("From Date cannot be after Cut-off Date.");
                    }
                    dialog.get_primary_btn().prop("disabled", true);
                    frappe.call({
                        method: "frappe.client.insert",
                        args: {doc: {doctype: "Bank Transaction GL Generation", ...values}},
                        callback: function (response) {
                            if (!response.message) return;
                            dialog.hide();
                            frappe.show_alert({message: "Background job queued. Results will appear on the generation run.", indicator: "blue"});
                            frappe.set_route("Form", "Bank Transaction GL Generation", response.message.name);
                        },
                        always: function () { dialog.get_primary_btn().prop("disabled", false); }
                    });
                }
            });
            dialog.show();
        });
        listview.page.add_menu_item("GL Generation Runs", function () {
            frappe.set_route("List", "Bank Transaction GL Generation");
        });
        listview.page.add_menu_item("Bank Transaction Statement", function () {
            frappe.set_route("query-report", "Bank Transaction Statement");
        });
    };
    frappe.listview_settings["Bank Transaction"] = settings;
})();
