frappe.pages["customer-statement"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Customer Statement"),
        single_column: true,
    });

    wrapper.customer_statement_page = new CustomerStatementPage(page);
};

frappe.pages["customer-statement"].on_page_show = function (wrapper) {
    if (wrapper.customer_statement_page) {
        wrapper.customer_statement_page.apply_route_customer();
    }
};

class CustomerStatementPage {
    constructor(page) {
        this.page = page;
        this.wrapper = $(page.body);
        this.statement_url = null;

        this.make_layout();
        this.make_filter_fields();
        this.make_email_fields();
        this.set_defaults();
        this.bind_actions();
    }

    make_layout() {
        this.wrapper.html(`
            <div class="customer-statement-page">
                <div class="customer-statement-card">
                    <div class="customer-statement-filter-row row"></div>
                </div>

                <div class="customer-statement-output mt-4" style="display: none;">
                    <div class="customer-statement-toolbar mb-3">
                        <button class="btn btn-default btn-sm customer-statement-print">
                            ${__("Print")}
                        </button>
                        <button class="btn btn-default btn-sm customer-statement-email-toggle">
                            ${__("Email Statement")}
                        </button>
                    </div>

                    <div class="customer-statement-email-panel mb-4" style="display: none;">
                        <div class="customer-statement-email-card">
                            <h4 class="mb-3">${__("Email Statement")}</h4>
                            <div class="row customer-statement-email-fields"></div>
                            <div class="mt-3">
                                <button class="btn btn-primary btn-sm customer-statement-send-email">
                                    ${__("Send Email")}
                                </button>
                            </div>
                        </div>
                    </div>

                    <div class="customer-statement-preview">
                        <iframe class="customer-statement-pdf-frame"></iframe>
                    </div>
                </div>
            </div>
        `);

        this.filter_row = this.wrapper.find(".customer-statement-filter-row");
        this.output = this.wrapper.find(".customer-statement-output");
        this.email_panel = this.wrapper.find(".customer-statement-email-panel");
        this.email_fields = this.wrapper.find(".customer-statement-email-fields");
        this.preview = this.wrapper.find(".customer-statement-preview");

        this.wrapper.find(".customer-statement-card, .customer-statement-email-card").css({
            border: "1px solid var(--border-color)",
            "border-radius": "8px",
            padding: "16px",
            background: "var(--card-bg)",
        });

        this.preview.css({
            border: "1px solid var(--border-color)",
            "border-radius": "8px",
            overflow: "hidden",
            height: "calc(100vh - 300px)",
            "min-height": "650px",
            background: "var(--card-bg)",
        });

        this.wrapper.find(".customer-statement-pdf-frame").css({
            width: "100%",
            height: "100%",
            border: "0",
        });
    }

    make_filter_fields() {
        this.customer_field = this.make_control(this.filter_row, {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer",
            reqd: 1,
        }, "col-md-4");

        this.from_date_field = this.make_control(this.filter_row, {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
        }, "col-md-3");

        this.to_date_field = this.make_control(this.filter_row, {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
        }, "col-md-3");

        const button_wrapper = $('<div class="col-md-2"></div>').appendTo(this.filter_row);
        button_wrapper.css("padding-top", "24px");
        button_wrapper.html(`
            <button class="btn btn-primary btn-sm customer-statement-generate">
                ${__("Generate Statement")}
            </button>
        `);

        for (const field of [this.customer_field, this.from_date_field, this.to_date_field]) {
            field.$input.on("change", () => this.clear_statement());
        }
    }

    make_email_fields() {
        this.primary_email_field = this.make_control(this.email_fields, {
            fieldname: "primary_email",
            label: __("Primary Email"),
            fieldtype: "Data",
            options: "Email",
        }, "col-md-6");

        this.additional_emails_field = this.make_control(this.email_fields, {
            fieldname: "additional_emails",
            label: __("Additional Email Addresses"),
            fieldtype: "Data",
            description: __("Separate multiple email addresses with commas."),
        }, "col-md-6");

        this.subject_field = this.make_control(this.email_fields, {
            fieldname: "subject",
            label: __("Subject"),
            fieldtype: "Data",
            reqd: 1,
        }, "col-md-12");

        this.message_field = this.make_control(this.email_fields, {
            fieldname: "message",
            label: __("Message"),
            fieldtype: "Text Editor",
            reqd: 1,
        }, "col-md-12");
    }

    make_control(parent, df, column_class) {
        const column = $(`<div class="${column_class}"></div>`).appendTo(parent);
        const control = frappe.ui.form.make_control({
            parent: column,
            df,
            render_input: true,
        });
        return control;
    }

    set_defaults() {
        const today = frappe.datetime.get_today();

        this.to_date_field.set_value(today);
        this.from_date_field.set_value(frappe.datetime.add_months(today, -1));

        this.apply_route_customer();
    }

    apply_route_customer() {
        let customer = null;

        if (frappe.route_options && frappe.route_options.customer) {
            customer = frappe.route_options.customer;
            frappe.route_options = null;
        }

        if (!customer && frappe.utils && frappe.utils.get_url_arg) {
            customer = frappe.utils.get_url_arg("customer");
        }

        if (customer && this.customer_field && this.customer_field.get_value() !== customer) {
            this.customer_field.set_value(customer);
        }
    }

    bind_actions() {
        this.wrapper.on("click", ".customer-statement-generate", () => {
            this.generate_statement();
        });

        this.wrapper.on("click", ".customer-statement-print", () => {
            this.print_statement();
        });

        this.wrapper.on("click", ".customer-statement-email-toggle", () => {
            this.email_panel.toggle();
        });

        this.wrapper.on("click", ".customer-statement-send-email", () => {
            this.send_email();
        });
    }

    get_filters() {
        return {
            customer: this.customer_field.get_value(),
            from_date: this.from_date_field.get_value(),
            to_date: this.to_date_field.get_value(),
        };
    }

    validate_filters() {
        const filters = this.get_filters();

        if (!filters.customer) {
            frappe.msgprint(__("Please select a Customer."));
            return false;
        }

        if (!filters.from_date || !filters.to_date) {
            frappe.msgprint(__("Please select From Date and To Date."));
            return false;
        }

        if (
            frappe.datetime.str_to_obj(filters.from_date) >
            frappe.datetime.str_to_obj(filters.to_date)
        ) {
            frappe.msgprint(__("From Date cannot be after To Date."));
            return false;
        }

        return true;
    }

    generate_statement() {
        if (!this.validate_filters()) {
            return;
        }

        const filters = this.get_filters();
        const method =
            "av_tools.sales.page.customer_statement.customer_statement.get_statement_pdf";

        this.statement_url =
            frappe.urllib.get_full_url(
                `/api/method/${method}` +
                    `?customer=${encodeURIComponent(filters.customer)}` +
                    `&from_date=${encodeURIComponent(filters.from_date)}` +
                    `&to_date=${encodeURIComponent(filters.to_date)}`
            );

        this.wrapper.find(".customer-statement-pdf-frame").attr("src", this.statement_url);
        this.output.show();
        this.email_panel.hide();

        this.load_customer_email_defaults(filters);
    }

    load_customer_email_defaults(filters) {
        frappe.call({
            method:
                "av_tools.sales.page.customer_statement.customer_statement.get_customer_details",
            args: {
                customer: filters.customer,
            },
            callback: (r) => {
                if (!r.message) {
                    return;
                }

                const customer_name = r.message.customer_name || filters.customer;

                this.primary_email_field.set_value(r.message.email_id || "");
                this.additional_emails_field.set_value("");
                this.subject_field.set_value(
                    __("Statement of Account - {0}", [customer_name])
                );
                this.message_field.set_value(
                    __(
                        "Please find attached your Statement of Account for the period {0} to {1}.",
                        [
                            frappe.datetime.str_to_user(filters.from_date),
                            frappe.datetime.str_to_user(filters.to_date),
                        ]
                    )
                );
            },
        });
    }

    print_statement() {
        if (!this.statement_url) {
            frappe.msgprint(__("Please generate the statement first."));
            return;
        }

        window.open(this.statement_url, "_blank");
    }

    send_email() {
        if (!this.validate_filters()) {
            return;
        }

        const filters = this.get_filters();

        frappe.call({
            method:
                "av_tools.sales.page.customer_statement.customer_statement.send_statement_email",
            args: {
                customer: filters.customer,
                from_date: filters.from_date,
                to_date: filters.to_date,
                primary_email: this.primary_email_field.get_value(),
                additional_emails: this.additional_emails_field.get_value(),
                subject: this.subject_field.get_value(),
                message: this.message_field.get_value(),
            },
            freeze: true,
            freeze_message: __("Sending customer statement..."),
            callback: (r) => {
                if (!r.exc && r.message && r.message.success) {
                    frappe.show_alert({
                        message: __("Customer statement email sent."),
                        indicator: "green",
                    });
                }
            },
        });
    }

    clear_statement() {
        this.statement_url = null;
        this.output.hide();
        this.email_panel.hide();
        this.wrapper.find(".customer-statement-pdf-frame").attr("src", "");
    }
}
