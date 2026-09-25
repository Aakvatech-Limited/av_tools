import frappe
from frappe.utils import cint
from frappe.utils.pdf import get_pdf
from frappe.www.printview import get_letter_head, get_print_style

from erpnext import get_company_currency
from erpnext.accounts.party import get_party_account_currency
from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import (
    get_common_filters,
    get_gl_filters,
    get_report_pdf,
    set_ageing,
)
from erpnext.accounts.report.general_ledger.general_ledger import execute as get_soa


DEFAULT_ORIENTATION = "Landscape"
DEFAULT_AGEING_BASED_ON = "Posting Date"


def get_customer_statement_settings(company):
    if not company or not frappe.db.exists("DocType", "Customer Statement Settings"):
        return None

    settings_name = frappe.db.get_value(
        "Customer Statement Settings",
        {
            "company": company,
            "disabled": 0,
        },
        "name",
    )

    if not settings_name:
        return None

    return frappe.get_cached_doc("Customer Statement Settings", settings_name)


def apply_statement_settings(statement, settings=None):
    settings = settings or get_customer_statement_settings(statement.company)

    if settings:
        statement.include_ageing = cint(settings.include_ageing)
        statement.ageing_based_on = settings.ageing_based_on or DEFAULT_AGEING_BASED_ON
        statement.orientation = settings.default_orientation or DEFAULT_ORIENTATION

        if cint(settings.use_company_letter_head):
            statement.letter_head = frappe.db.get_value(
                "Company",
                statement.company,
                "default_letter_head",
            )
        else:
            statement.letter_head = None
    else:
        statement.include_ageing = 1
        statement.ageing_based_on = DEFAULT_AGEING_BASED_ON
        statement.orientation = DEFAULT_ORIENTATION
        statement.letter_head = frappe.db.get_value(
            "Company",
            statement.company,
            "default_letter_head",
        )

    statement.posting_date = statement.to_date
    return settings


def get_customer_statement_pdf(statement):
    settings = get_customer_statement_settings(statement.company)
    apply_statement_settings(statement, settings)

    if settings and settings.customer_statement_print_format:
        return _get_custom_print_format_pdf(
            statement,
            settings.customer_statement_print_format,
        )

    return get_report_pdf(statement)


def get_email_defaults(company, customer, from_date, to_date):
    settings = get_customer_statement_settings(company)
    customer_doc = frappe.get_cached_doc("Customer", customer)
    company_doc = frappe.get_cached_doc("Company", company)

    context = {
        "customer": customer_doc,
        "company": company_doc,
        "from_date": from_date,
        "to_date": to_date,
    }

    subject_template = (
        settings.default_email_subject
        if settings and settings.default_email_subject
        else "Statement of Account - {{ customer.customer_name }}"
    )
    message_template = (
        settings.default_email_message
        if settings and settings.default_email_message
        else (
            "Please find attached your Statement of Account for the period "
            "{{ from_date }} to {{ to_date }}."
        )
    )

    return {
        "subject": frappe.render_template(subject_template, context),
        "message": frappe.render_template(message_template, context),
    }


def _get_custom_print_format_pdf(statement, print_format_name):
    print_format = frappe.get_cached_doc("Print Format", print_format_name)
    context = _build_print_context(statement)

    if not context:
        return False

    body = frappe.render_template(print_format.html or "", context)

    css = get_print_style(print_format=print_format)

    html = frappe.render_template(
        "frappe/www/printview.html",
        {
            "body": body,
            "print_style": css,
            "title": "Statement For " + statement.customers[0].customer,
            "lang": getattr(frappe.local, "lang", None) or "en",
            "layout_direction": (
                "rtl"
                if (getattr(frappe.local, "lang", None) or "en") in ("ar", "he", "fa", "ur")
                else "ltr"
            ),
        },
    )

    options = {
        "orientation": statement.orientation or DEFAULT_ORIENTATION,
    }

    margin_fields = {
        "margin_top": "margin-top",
        "margin_bottom": "margin-bottom",
        "margin_left": "margin-left",
        "margin_right": "margin-right",
    }

    for fieldname, option_name in margin_fields.items():
        value = print_format.get(fieldname)
        if value is not None:
            options[option_name] = str(value) + "mm"

    return get_pdf(html, options)


def _build_print_context(statement):
    entry = statement.customers[0]
    customer_doc = frappe.get_cached_doc("Customer", entry.customer)
    company_doc = frappe.get_cached_doc("Company", statement.company)

    tax_id = customer_doc.tax_id
    presentation_currency = (
        statement.currency
        or get_party_account_currency("Customer", entry.customer, statement.company)
        or get_company_currency(statement.company)
    )

    filters = get_common_filters(statement)

    if statement.ignore_exchange_rate_revaluation_journals:
        filters.update({"ignore_err": True})

    if statement.ignore_cr_dr_notes:
        filters.update({"ignore_cr_dr_notes": True})

    filters.update(
        get_gl_filters(
            statement,
            entry,
            tax_id,
            presentation_currency,
        )
    )

    columns, data = get_soa(filters)

    for index in [0, -2, -1]:
        if data and len(data) >= abs(index) and data[index].get("account"):
            data[index]["account"] = data[index]["account"].replace("'", "")

    if len(data) == 3:
        return None

    ageing_data = []
    if statement.include_ageing:
        ageing_data = set_ageing(statement, entry)

    letter_head = None
    if statement.letter_head:
        letter_head = get_letter_head(statement, 0)

    terms_and_conditions = None
    if statement.terms_and_conditions:
        terms_and_conditions = frappe.db.get_value(
            "Terms and Conditions",
            statement.terms_and_conditions,
            "terms",
        )

    return {
        "doc": statement,
        "customer": customer_doc,
        "company": company_doc,
        "filters": filters,
        "data": data,
        "columns": columns,
        "report": {
            "report_name": statement.report,
            "columns": columns,
        },
        "ageing": ageing_data[0] if statement.include_ageing and ageing_data else None,
        "ageing_data": ageing_data,
        "letter_head": letter_head,
        "terms_and_conditions": terms_and_conditions,
        "from_date": statement.from_date,
        "to_date": statement.to_date,
    }
