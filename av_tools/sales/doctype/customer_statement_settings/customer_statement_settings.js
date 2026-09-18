frappe.ui.form.on("Customer Statement Settings", {
    setup(frm) {
        frm.set_query("customer_statement_print_format", function () {
            return {
                filters: {
                    print_format_for: "DocType",
                    doc_type: "Process Statement Of Accounts",
                    custom_format: 1,
                    print_format_type: "Jinja",
                    disabled: 0,
                },
            };
        });
    },
});
