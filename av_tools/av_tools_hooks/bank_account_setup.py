"""Create an ERPNext Bank Account for an existing Bank-type GL Account."""

import frappe
from frappe import _
from frappe.utils import cint


def _validate_account(account):
    if not account:
        frappe.throw(_("Account is required."))
    doc = frappe.get_doc("Account", account)
    doc.check_permission("read")
    if doc.account_type != "Bank" or cint(doc.is_group):
        frappe.throw(_("Only a leaf Account with Account Type Bank can be configured."))
    if not doc.company:
        frappe.throw(_("The Account must belong to a Company."))
    return doc


def _existing_bank_account(account):
    return frappe.db.get_value(
        "Bank Account",
        {"account": account, "is_company_account": 1},
        "name",
    )


@frappe.whitelist()
def get_bank_setup_status(account):
    """Return setup eligibility without changing any records."""
    doc = _validate_account(account)
    existing = _existing_bank_account(doc.name)
    return {
        "account": doc.name,
        "company": doc.company,
        "currency": doc.account_currency,
        "account_name": doc.account_name,
        "bank_account": existing,
        "can_create": bool(frappe.has_permission("Bank Account", "create")),
    }


@frappe.whitelist()
def create_bank_account_from_ledger(
    account,
    account_name,
    bank=None,
    new_bank_name=None,
    bank_account_no=None,
    branch_code=None,
    iban=None,
    is_default=0,
):
    """Create/link records atomically; normal Frappe permissions are enforced.

    Locking the Account row serializes concurrent setup requests for a ledger.
    The request transaction is committed by Frappe only after successful return.
    """
    doc = _validate_account(account)
    if not frappe.has_permission("Bank Account", "create"):
        frappe.throw(_("You do not have permission to create Bank Accounts."), frappe.PermissionError)

    # Serialize requests originating from separate tabs/users.
    frappe.db.sql("SELECT name FROM `tabAccount` WHERE name = %s FOR UPDATE", doc.name)
    existing = _existing_bank_account(doc.name)
    if existing:
        return {"name": existing, "created": False}

    account_name = (account_name or "").strip()
    bank = (bank or "").strip()
    new_bank_name = (new_bank_name or "").strip()
    if not account_name:
        frappe.throw(_("Bank Account Name is required."))
    if bool(bank) == bool(new_bank_name):
        frappe.throw(_("Select an existing Bank or provide a new Bank name."))

    if new_bank_name:
        if frappe.db.exists("Bank", new_bank_name):
            frappe.throw(_("Bank {0} already exists. Please select it instead.").format(frappe.bold(new_bank_name)))
        if not frappe.has_permission("Bank", "create"):
            frappe.throw(_("You do not have permission to create a Bank."), frappe.PermissionError)
        bank_doc = frappe.get_doc({"doctype": "Bank", "bank_name": new_bank_name})
        bank_doc.insert()
        bank = bank_doc.name
    else:
        bank_doc = frappe.get_doc("Bank", bank)
        bank_doc.check_permission("read")

    values = {
        "doctype": "Bank Account",
        "account_name": account_name,
        "bank": bank,
        "bank_account_no": (bank_account_no or "").strip(),
        "account": doc.name,
        "company": doc.company,
        "is_company_account": 1,
        "is_default": cint(is_default),
    }
    meta = frappe.get_meta("Bank Account")
    if meta.has_field("branch_code"):
        values["branch_code"] = (branch_code or "").strip()
    if meta.has_field("iban"):
        values["iban"] = (iban or "").strip()
    result = frappe.get_doc(values)
    result.insert()
    return {"name": result.name, "created": True}
