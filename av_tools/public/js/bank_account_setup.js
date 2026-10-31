/* Bank Account setup for an existing Bank-type ledger. */
(() => {
    const method = "av_tools.av_tools_hooks.bank_account_setup";
    const eligible = (frm) => !frm.is_new() && frm.doc.account_type === "Bank" && !frm.doc.is_group;

    async function refresh_bank_setup(frm) {
        if (!eligible(frm)) return;
        const name = frm.doc.name;
        try {
            const response = await frappe.call({
                method: method + ".get_bank_setup_status",
                args: { account: name },
            });
            if (frm.doc.name !== name || !eligible(frm)) return;
            const status = response.message;
            if (!status) return;
            if (status.bank_account) {
                frm.add_custom_button(__("View Bank Account"), () => {
                    frappe.set_route("Form", "Bank Account", status.bank_account);
                }, __("Banking"));
            } else if (status.can_create) {
                frm.add_custom_button(__("Set Up Bank Account"), () => show_setup(frm, status), __("Banking"));
                if (frm.__av_bank_prompt_after_save) {
                    frm.__av_bank_prompt_after_save = false;
                    show_setup(frm, status);
                }
            }
        } catch (error) {
            // Do not interfere with opening the Account form.
            console.warn("Bank Account setup status unavailable", error);
        }
    }

    function show_setup(frm, status) {
        if (frm.__av_bank_dialog?.display) return;
        const dialog = new frappe.ui.Dialog({
            title: __("Set Up Bank Account"),
            fields: [
                { fieldname: "details", fieldtype: "HTML", options:
                    `<div class="small text-muted mb-3">${frappe.utils.escape_html(status.account)} &middot; ${frappe.utils.escape_html(status.company)} &middot; ${frappe.utils.escape_html(status.currency || "")}</div>` },
                { fieldname: "account_name", fieldtype: "Data", label: __("Bank Account Name"), reqd: 1, default: status.account_name },
                { fieldname: "bank_mode", fieldtype: "Select", label: __("Bank Selection"), options: ["Existing Bank", "New Bank"], default: "Existing Bank", reqd: 1 },
                { fieldname: "bank", fieldtype: "Link", options: "Bank", label: __("Bank"), mandatory_depends_on: 'eval:doc.bank_mode=="Existing Bank"', depends_on: 'eval:doc.bank_mode=="Existing Bank"' },
                { fieldname: "new_bank_name", fieldtype: "Data", label: __("New Bank Name"), mandatory_depends_on: 'eval:doc.bank_mode=="New Bank"', depends_on: 'eval:doc.bank_mode=="New Bank"' },
                { fieldname: "bank_account_no", fieldtype: "Data", label: __("Bank Account Number") },
                { fieldname: "branch_code", fieldtype: "Data", label: __("Branch / Routing Code") },
                { fieldname: "iban", fieldtype: "Data", label: __("IBAN") },
                { fieldname: "is_default", fieldtype: "Check", label: __("Set as Default Bank Account") },
            ],
            primary_action_label: __("Create Bank Account"),
            primary_action: async (values) => {
                const args = {
                    account: status.account,
                    account_name: values.account_name,
                    bank: values.bank_mode === "Existing Bank" ? values.bank : null,
                    new_bank_name: values.bank_mode === "New Bank" ? values.new_bank_name : null,
                    bank_account_no: values.bank_account_no,
                    branch_code: values.branch_code,
                    iban: values.iban,
                    is_default: values.is_default,
                };
                dialog.get_primary_btn().prop("disabled", true);
                try {
                    const result = await frappe.call({ method: method + ".create_bank_account_from_ledger", args });
                    dialog.hide();
                    if (result.message?.name) {
                        frappe.show_alert({
                            message: result.message.created ? __("Bank Account created") : __("Bank Account already configured"),
                            indicator: "green",
                        });
                        frm.reload_doc();
                    }
                } finally {
                    dialog.get_primary_btn().prop("disabled", false);
                }
            },
        });
        frm.__av_bank_dialog = dialog;
        dialog.$wrapper.on("hidden.bs.modal", () => { frm.__av_bank_dialog = null; });
        dialog.show();
    }

    frappe.ui.form.on("Account", {
        before_save(frm) {
            if (frm.is_new() && frm.doc.account_type === "Bank" && !frm.doc.is_group) {
                frm.__av_bank_prompt_after_save = true;
            }
        },
        refresh(frm) {
            refresh_bank_setup(frm);
        },
    });
})();
