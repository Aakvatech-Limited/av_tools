import frappe
from frappe import _
from frappe.model.document import Document


class CustomerStatementSettings(Document):
    def validate(self):
        self.validate_print_format()

    def validate_print_format(self):
        if not self.customer_statement_print_format:
            return

        print_format = frappe.db.get_value(
            "Print Format",
            self.customer_statement_print_format,
            [
                "print_format_for",
                "doc_type",
                "custom_format",
                "disabled",
                "print_format_type",
            ],
            as_dict=True,
        )

        if not print_format:
            frappe.throw(_("Customer Statement Print Format does not exist."))

        if print_format.print_format_for != "DocType":
            frappe.throw(_("Customer Statement Print Format must be for a DocType."))

        if print_format.doc_type != "Process Statement Of Accounts":
            frappe.throw(
                _(
                    "Customer Statement Print Format must be for "
                    "Process Statement Of Accounts."
                )
            )

        if not print_format.custom_format or print_format.print_format_type != "Jinja":
            frappe.throw(_("Customer Statement Print Format must be a custom Jinja Print Format."))

        if print_format.disabled:
            frappe.throw(_("Customer Statement Print Format cannot be disabled."))
