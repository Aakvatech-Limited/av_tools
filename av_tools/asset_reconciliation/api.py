"""Read-only Asset reconciliation APIs. No accounting documents are written here."""

import frappe
from frappe.utils import flt

RECONCILIATION = "Asset Capitalization Reconciliation"


@frappe.whitelist()
@frappe.read_only()
def asset_accounting_audit(asset):
    doc = frappe.get_doc("Asset", asset)
    doc.check_permission("read")
    required = {"asset_name", "status", "total_asset_cost", "value_after_depreciation", "journal_entry_for_scrap", "company"}
    allowed = set(frappe.get_meta("Asset").get_permitted_fieldnames())
    if required - allowed:
        frappe.throw("You do not have permission to read the Asset accounting fields.", frappe.PermissionError)
    frappe.has_permission("GL Entry", "read", throw=True)
    entries = frappe.get_list(
        "GL Entry",
        filters={"against_voucher_type": "Asset", "against_voucher": doc.name,
                 "company": doc.company, "is_cancelled": 0},
        fields=["name", "posting_date", "voucher_type", "voucher_no", "account", "debit", "credit"],
        order_by="posting_date asc, name asc", limit_page_length=501,
    )
    truncated = len(entries) > 500
    entries = entries[:500]
    return {
        "asset": doc.name, "asset_name": doc.asset_name, "status": doc.status,
        "cost": doc.total_asset_cost, "header_book_value": doc.value_after_depreciation,
        "scrap_journal": doc.journal_entry_for_scrap,
        "currency": frappe.get_cached_value("Company", doc.company, "default_currency"),
        "entries": entries, "total_debit": sum(flt(e.debit) for e in entries),
        "total_credit": sum(flt(e.credit) for e in entries), "truncated": truncated,
    }


@frappe.whitelist()
@frappe.read_only()
def asset_capitalization_reconciliation_links(reference_doctype, reference_name):
    if reference_doctype not in ("Asset", "Purchase Invoice", "Journal Entry") or not reference_name:
        frappe.throw("A valid Asset, Purchase Invoice or Journal Entry is required.")
    frappe.get_doc(reference_doctype, reference_name).check_permission("read")
    if reference_doctype == "Asset":
        filters = [["Asset Reconciliation Asset", "asset", "=", reference_name]]
    else:
        filters = [
            ["Asset Reconciliation Source", "source_voucher_type", "=", reference_doctype],
            ["Asset Reconciliation Source", "source_voucher", "=", reference_name],
        ]
    matches = frappe.get_list(
        RECONCILIATION, filters=filters, fields=["name", "status", "reconciliation_date", "basis"],
        distinct=True, limit_page_length=0, order_by="reconciliation_date desc, name asc",
    )
    return {"matches": matches, "count": len(matches)}
