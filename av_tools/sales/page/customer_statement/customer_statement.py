import frappe
from frappe import _
from frappe.utils import getdate, validate_email_address

from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import (
    get_report_pdf,
)


def _get_company():
    company = frappe.defaults.get_user_default("Company")

    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company")

    if not company:
        frappe.throw(_("Please set a default Company before generating a customer statement."))

    return company


def _validate_dates(from_date, to_date):
    if not from_date or not to_date:
        frappe.throw(_("From Date and To Date are required."))

    if getdate(from_date) > getdate(to_date):
        frappe.throw(_("From Date cannot be after To Date."))


def _parse_recipients(primary_email=None, additional_emails=None):
    recipients = []

    for value in (primary_email or "", additional_emails or ""):
        for email in value.replace(";", ",").split(","):
            email = email.strip()
            if not email:
                continue

            validate_email_address(email, throw=True)

            if email not in recipients:
                recipients.append(email)

    return recipients


def _build_statement_doc(customer, from_date, to_date):
    frappe.has_permission("Customer", "read", customer, throw=True)
    _validate_dates(from_date, to_date)

    company = _get_company()
    customer_doc = frappe.get_cached_doc("Customer", customer)

    statement = frappe.new_doc("Process Statement Of Accounts")
    statement.company = company
    statement.report = "General Ledger"
    statement.from_date = from_date
    statement.to_date = to_date
    statement.include_ageing = 1
    statement.ageing_based_on = "Posting Date"
    statement.posting_date = to_date
    statement.show_remarks = 1
    statement.orientation = "Landscape"

    statement.letter_head = frappe.db.get_value("Company", company, "default_letter_head")

    statement.append(
        "customers",
        {
            "customer": customer_doc.name,
            "customer_name": customer_doc.customer_name,
            "primary_email": customer_doc.email_id or "",
        },
    )

    return statement


def _get_pdf(customer, from_date, to_date):
    statement = _build_statement_doc(customer, from_date, to_date)
    pdf = get_report_pdf(statement)

    if not pdf:
        frappe.throw(
            _("No General Ledger transactions were found for this customer in the selected period.")
        )

    return pdf


def _get_filename(customer, from_date, to_date):
    customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
    return _("Customer Statement - {0} - {1} to {2}.pdf").format(
        customer_name,
        from_date,
        to_date,
    )


@frappe.whitelist()
def get_customer_details(customer):
    frappe.has_permission("Customer", "read", customer, throw=True)

    return frappe.db.get_value(
        "Customer",
        customer,
        ["name", "customer_name", "email_id"],
        as_dict=True,
    )


@frappe.whitelist()
def get_statement_pdf(customer, from_date, to_date):
    pdf = _get_pdf(customer, from_date, to_date)

    frappe.local.response.filename = _get_filename(customer, from_date, to_date)
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "pdf"


@frappe.whitelist()
def send_statement_email(
    customer,
    from_date,
    to_date,
    primary_email=None,
    additional_emails=None,
    subject=None,
    message=None,
):
    frappe.has_permission("Customer", "read", customer, throw=True)
    _validate_dates(from_date, to_date)

    recipients = _parse_recipients(primary_email, additional_emails)

    if not recipients:
        frappe.throw(_("Please enter at least one email recipient."))

    customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
    subject = subject or _("Statement of Account - {0}").format(customer_name)
    message = message or _(
        "Please find attached your Statement of Account for the period {0} to {1}."
    ).format(from_date, to_date)

    pdf = _get_pdf(customer, from_date, to_date)
    filename = _get_filename(customer, from_date, to_date)

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        attachments=[
            {
                "fname": filename,
                "fcontent": pdf,
            }
        ],
        reference_doctype="Customer",
        reference_name=customer,
    )

    return {
        "success": True,
        "recipients": recipients,
    }
