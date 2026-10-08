# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

MAX_CANDIDATES = 200
CORE_SOURCES = ("Payment Entry", "Journal Entry", "Purchase Invoice", "Sales Invoice")


def supported_sources():
    """Respect the site's actual ERPNext/Frappe reconciliation registry."""
    sources = frappe.get_hooks("bank_reconciliation_doctypes") or []
    return list(dict.fromkeys(dt for dt in sources if frappe.db.exists("DocType", dt)))


@frappe.whitelist()
def get_supported_sources():
    frappe.only_for(("Accounts Manager", "System Manager"))
    return supported_sources()


def _validate_criteria(doc):
    if doc.source_doctype not in supported_sources():
        frappe.throw(_("Source DocType is not registered for Bank Transaction reconciliation."))
    if not doc.company or not doc.from_date or not doc.to_date:
        frappe.throw(_("Company and both clearance dates are required."))
    if getdate(doc.from_date) > getdate(doc.to_date):
        frappe.throw(_("From Date must not exceed To Date."))
    if doc.source_doctype != "Sales Invoice":
        meta = frappe.get_meta(doc.source_doctype)
        if not meta.has_field("clearance_date") or not meta.has_field("company"):
            frappe.throw(
                _("Reconciliation source {0} needs company and clearance_date fields for automatic backfill.").format(doc.source_doctype)
            )


def _bank_accounts(company):
    mapping = {}
    for row in frappe.get_all("Bank Account", filters={"company": company}, fields=["name", "account"]):
        if row.account:
            mapping.setdefault(row.account, []).append(row.name)
    return mapping


def _existing(doctype, name):
    refs = frappe.get_all(
        "Bank Transaction Payments",
        filters={"payment_document": doctype, "payment_entry": name, "parenttype": "Bank Transaction"},
        pluck="parent",
        limit_page_length=500,
    )
    return any(frappe.db.get_value("Bank Transaction", bt, "docstatus") != 2 for bt in refs)


def _bank_gl(doctype, name, company, accounts):
    rows = frappe.get_all(
        "GL Entry",
        filters={"voucher_type": doctype, "voucher_no": name, "company": company, "is_cancelled": 0},
        fields=["account", "debit_in_account_currency", "credit_in_account_currency"],
        limit_page_length=1000,
    )
    totals = {}
    for row in rows:
        if row.account in accounts:
            # Reconciliation uses absolute individual bank-side GL movements, including same-account offsets.
            totals[row.account] = totals.get(row.account, 0) + abs(
                flt(row.debit_in_account_currency) - flt(row.credit_in_account_currency)
            )
    return totals


def _source_rows(doc):
    dt = doc.source_doctype
    if dt == "Sales Invoice":
        # POS payments are tracked individually, and clearance_date belongs to the child row.
        payments = frappe.get_all(
            "Sales Invoice Payment",
            filters={"clearance_date": ["between", [doc.from_date, doc.to_date]]},
            fields=["parent", "name", "account", "clearance_date", "amount"],
            order_by="parent asc, clearance_date asc",
            limit_page_length=MAX_CANDIDATES * 20 + 1,
        )
        if len(payments) > MAX_CANDIDATES * 20:
            frappe.throw(_("Too many Sales Invoice payment rows. Narrow the date range."))
        parents = set(p.parent for p in payments)
        valid_parents = set()
        if parents:
            valid_parents = set(frappe.get_all(
                "Sales Invoice", filters={"name": ["in", list(parents)], "company": doc.company, "docstatus": 1},
                pluck="name", limit_page_length=len(parents),
            ))
        return [
            frappe._dict(name=p.parent, clearance_date=p.clearance_date, account=p.account,
                payment_row=p.name, amount=p.amount)
            for p in payments if p.parent in valid_parents and flt(p.amount) > 0
        ]

    rows = frappe.get_all(
        dt,
        filters={"company": doc.company, "docstatus": 1, "clearance_date": ["between", [doc.from_date, doc.to_date]]},
        fields=["name", "clearance_date"],
        order_by="clearance_date asc, name asc",
        limit_page_length=MAX_CANDIDATES + 1,
    )
    if len(rows) > MAX_CANDIDATES:
        frappe.throw(_("More than {0} source vouchers match. Narrow the date range.").format(MAX_CANDIDATES))
    return rows


def _candidates(doc):
    _validate_criteria(doc)
    mapping = _bank_accounts(doc.company)
    source_rows = _source_rows(doc)
    candidates = {}
    for source in source_rows:
        if _existing(doc.source_doctype, source.name):
            continue
        if doc.source_doctype == "Purchase Invoice":
            invoice = frappe.db.get_value("Purchase Invoice", source.name,
                ["is_paid", "cash_bank_account"], as_dict=True)
            if not invoice or not invoice.is_paid or not invoice.cash_bank_account:
                continue
        totals = _bank_gl(doc.source_doctype, source.name, doc.company, mapping)
        for account, gl_amount in totals.items():
            if len(mapping[account]) != 1 or not flt(gl_amount, 2):
                continue
            if doc.source_doctype == "Purchase Invoice" and account != invoice.cash_bank_account:
                continue
            if doc.source_doctype == "Sales Invoice" and account != source.account:
                continue
            # One Bank Transaction per voucher + bank account. Multiple invoice payment
            # rows must share one clearance date and their sum must match the bank GL.
            key = (source.name, account)
            if doc.source_doctype == "Sales Invoice":
                entry = candidates.setdefault(key, {
                    "source_doctype": doc.source_doctype, "source_document": source.name,
                    "bank_account": mapping[account][0], "clearance_date": str(source.clearance_date),
                    "deposit": 0, "withdrawal": 0, "status": "Pending",
                    "_amount": 0, "_invalid": False,
                })
                entry["_amount"] += flt(source.amount)
                if entry["clearance_date"] != str(source.clearance_date):
                    entry["_invalid"] = True
            else:
                # Direction derives from net bank GL movements.
                signed = frappe.get_all("GL Entry", filters={
                    "voucher_type": doc.source_doctype, "voucher_no": source.name,
                    "account": account, "is_cancelled": 0,
                }, fields=["debit_in_account_currency", "credit_in_account_currency"],
                    limit_page_length=1000)
                net = sum(flt(r.debit_in_account_currency) - flt(r.credit_in_account_currency) for r in signed)
                if abs(abs(net) - gl_amount) > 0.01:
                    continue  # Mixed directions in the same bank account need manual review.
                candidates[key] = {
                    "source_doctype": doc.source_doctype, "source_document": source.name,
                    "bank_account": mapping[account][0], "clearance_date": str(source.clearance_date),
                    "deposit": flt(net, 2) if net > 0 else 0,
                    "withdrawal": abs(flt(net, 2)) if net < 0 else 0, "status": "Pending",
                }

    results = []
    for (source_name, account), entry in candidates.items():
        if doc.source_doctype == "Sales Invoice":
            if entry.pop("_invalid") or abs(entry.pop("_amount") - _bank_gl(
                doc.source_doctype, source_name, doc.company, mapping).get(account, 0)
            ) > 0.01:
                continue
            entry["deposit"] = flt(_bank_gl(doc.source_doctype, source_name, doc.company, mapping)[account], 2)
        results.append(entry)
    if len(results) > MAX_CANDIDATES:
        frappe.throw(_("More than {0} candidate transactions match. Narrow the date range.").format(MAX_CANDIDATES))
    return results


@frappe.whitelist()
def preview_candidates(name):
    doc = frappe.get_doc("Bank Transaction Backfill", name)
    doc.check_permission("write")
    if doc.docstatus:
        frappe.throw(_("Only draft backfills can be previewed."))
    return _candidates(doc)


def _candidate_matches(row, expected):
    return (
        str(row.clearance_date) == str(expected["clearance_date"])
        and row.source_doctype == expected["source_doctype"]
        and row.bank_account == expected["bank_account"]
        and abs(flt(row.deposit) - flt(expected["deposit"])) <= 0.001
        and abs(flt(row.withdrawal) - flt(expected["withdrawal"])) <= 0.001
    )


class BankTransactionBackfill(Document):
    def validate(self):
        _validate_criteria(self)

    def before_submit(self):
        self.check_permission("submit")
        if not self.entries:
            frappe.throw(_("Preview and save candidates first."))
        keys = [(r.source_document, r.bank_account) for r in self.entries]
        if len(keys) != len(set(keys)):
            frappe.throw(_("Duplicate source / Bank Account rows are not allowed."))
        expected = {(r["source_document"], r["bank_account"]): r for r in _candidates(self)}
        for row in self.entries:
            match = expected.get((row.source_document, row.bank_account))
            if not match or not _candidate_matches(row, match):
                frappe.throw(_("Candidate {0} has changed or is unsupported. Refresh the preview.").format(row.source_document))

    def on_submit(self):
        counts = {"Created": 0, "Skipped": 0, "Failed": 0}
        for row in self.entries:
            frappe.db.savepoint("bt_backfill_" + str(row.idx))
            try:
                current = {
                    (r["source_document"], r["bank_account"]): r
                    for r in _candidates(self)
                }.get((row.source_document, row.bank_account))
                if not current or not _candidate_matches(row, current):
                    status, message, bt_name = "Skipped", "No longer eligible or source changed", None
                else:
                    linked_account = frappe.db.get_value("Bank Account", row.bank_account, "account")
                    bt = frappe.get_doc({
                        "doctype": "Bank Transaction",
                        "date": row.clearance_date,
                        "bank_account": row.bank_account,
                        "company": self.company,
                        "currency": frappe.db.get_value("Account", linked_account, "account_currency"),
                        "deposit": row.deposit,
                        "withdrawal": row.withdrawal,
                        "reference_number": row.source_document,
                        "description": "Backfill " + self.name + " / " + self.source_doctype + " " + row.source_document,
                        "payment_entries": [{
                            "payment_document": self.source_doctype,
                            "payment_entry": row.source_document,
                            "allocated_amount": 0,
                        }],
                    })
                    bt.insert()
                    bt.submit()
                    status, message, bt_name = "Created", "", bt.name
            except Exception as exc:
                frappe.db.rollback(save_point="bt_backfill_" + str(row.idx))
                status, message, bt_name = "Failed", str(exc)[:500], None
            counts[status] += 1
            frappe.db.set_value("Bank Transaction Backfill Entry", row.name, {
                "status": status, "error_message": message, "bank_transaction": bt_name,
            }, update_modified=False)
        frappe.db.set_value(self.doctype, self.name, {
            "created_count": counts["Created"], "skipped_count": counts["Skipped"],
            "failed_count": counts["Failed"],
        }, update_modified=False)

    def before_cancel(self):
        frappe.throw(_("Submitted backfill audit records cannot be cancelled."))
