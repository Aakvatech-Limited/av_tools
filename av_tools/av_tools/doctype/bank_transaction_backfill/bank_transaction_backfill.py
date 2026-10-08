# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

SUPPORTED = ("Payment Entry", "Journal Entry")
MAX_CANDIDATES = 200


def _validate_criteria(doc):
    if doc.source_doctype not in SUPPORTED:
        frappe.throw(_("Select Payment Entry or Journal Entry."))
    if not doc.company or not doc.from_date or not doc.to_date:
        frappe.throw(_("Company and both clearance dates are required."))
    if getdate(doc.from_date) > getdate(doc.to_date):
        frappe.throw(_("From Date must not exceed To Date."))


def _bank_accounts(company):
    rows = frappe.get_all(
        "Bank Account",
        filters={"company": company},
        fields=["name", "account"],
    )
    accounts = {}
    for row in rows:
        if row.account:
            accounts.setdefault(row.account, []).append(row.name)
    return accounts


def _existing_bank_transaction(doctype, name):
    references = frappe.get_all(
        "Bank Transaction Payments",
        filters={"payment_document": doctype, "payment_entry": name, "parenttype": "Bank Transaction"},
        fields=["parent"],
        limit_page_length=100,
    )
    for ref in references:
        if frappe.db.get_value("Bank Transaction", ref.parent, "docstatus") != 2:
            return ref.parent
    return None


def _voucher_candidates(doc, voucher, accounts):
    existing = _existing_bank_transaction(doc.source_doctype, voucher.name)
    if existing:
        return []
    gl = frappe.get_all(
        "GL Entry",
        filters={
            "voucher_type": doc.source_doctype,
            "voucher_no": voucher.name,
            "company": doc.company,
            "is_cancelled": 0,
        },
        fields=["account", "debit_in_account_currency", "credit_in_account_currency"],
        limit_page_length=1000,
    )
    sums = {}
    for entry in gl:
        if entry.account not in accounts:
            continue
        sums[entry.account] = sums.get(entry.account, 0) + flt(entry.debit_in_account_currency) - flt(entry.credit_in_account_currency)
    result = []
    for account, amount in sums.items():
        matches = accounts[account]
        if len(matches) != 1 or not flt(amount, 2):
            continue
        result.append({
            "source_document": voucher.name,
            "source_doctype": doc.source_doctype,
            "bank_account": matches[0],
            "clearance_date": str(voucher.clearance_date),
            "deposit": flt(amount, 2) if amount > 0 else 0,
            "withdrawal": abs(flt(amount, 2)) if amount < 0 else 0,
            "status": "Pending",
        })
    return result


def _candidates(doc):
    _validate_criteria(doc)
    accounts = _bank_accounts(doc.company)
    vouchers = frappe.get_all(
        doc.source_doctype,
        filters={
            "company": doc.company,
            "docstatus": 1,
            "clearance_date": ["between", [doc.from_date, doc.to_date]],
        },
        fields=["name", "clearance_date"],
        order_by="clearance_date asc, name asc",
        limit_page_length=MAX_CANDIDATES + 1,
    )
    if len(vouchers) > MAX_CANDIDATES:
        frappe.throw(_("More than {0} source vouchers match. Narrow the date range.").format(MAX_CANDIDATES))
    result = []
    for voucher in vouchers:
        result.extend(_voucher_candidates(doc, voucher, accounts))
    return result


@frappe.whitelist()
def preview_candidates(name):
    doc = frappe.get_doc("Bank Transaction Backfill", name)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("Only draft backfills can be previewed."))
    return _candidates(doc)


class BankTransactionBackfill(Document):
    def validate(self):
        _validate_criteria(self)
        if len(self.entries or []) > MAX_CANDIDATES * 3:
            frappe.throw(_("Too many candidate rows; narrow the date range."))

    def before_submit(self):
        self.check_permission("submit")
        if not self.entries:
            frappe.throw(_("Preview and save eligible candidates before submitting."))
        keys = [(r.source_document, r.bank_account) for r in self.entries]
        if any(r.source_doctype != self.source_doctype for r in self.entries):
            frappe.throw(_("Source DocType mismatch in candidate rows."))
        if len(keys) != len(set(keys)):
            frappe.throw(_("Duplicate candidate rows are not permitted."))
        eligible = {(r["source_document"], r["bank_account"]): r for r in _candidates(self)}
        for row in self.entries:
            candidate = eligible.get((row.source_document, row.bank_account))
            if not candidate:
                frappe.throw(_("Candidate {0} is no longer eligible; refresh the preview.").format(row.source_document))
            for field in ("clearance_date", "deposit", "withdrawal"):
                if str(candidate[field]) != str(row.get(field)) and (
                    field == "clearance_date" or abs(flt(candidate[field]) - flt(row.get(field))) > 0.001
                ):
                    frappe.throw(_("Candidate {0} changed; refresh the preview.").format(row.source_document))
        if len(self.entries) > MAX_CANDIDATES:
            frappe.throw(_("Maximum {0} entries per backfill.").format(MAX_CANDIDATES))

    def _candidate_is_current(self, row):
        voucher = frappe._dict(name=row.source_document, clearance_date=row.clearance_date)
        candidates = _voucher_candidates(self, voucher, _bank_accounts(self.company))
        return any(
            c["bank_account"] == row.bank_account
            and abs(flt(c["deposit"]) - flt(row.deposit)) < 0.001
            and abs(flt(c["withdrawal"]) - flt(row.withdrawal)) < 0.001
            for c in candidates
        )

    def on_submit(self):
        counts = {"Created": 0, "Skipped": 0, "Failed": 0}
        for row in self.entries:
            savepoint = "backfill_entry_" + str(row.idx)
            frappe.db.savepoint(savepoint)
            try:
                if _existing_bank_transaction(self.source_doctype, row.source_document):
                    state, detail, transaction = "Skipped", "Existing Bank Transaction allocation found", None
                else:
                    source = frappe.db.get_value(
                        self.source_doctype, row.source_document,
                        ["docstatus", "clearance_date", "company"], as_dict=True,
                    )
                    if not source or source.docstatus != 1 or source.company != self.company or str(source.clearance_date) != str(row.clearance_date):
                        state, detail, transaction = "Skipped", "Source voucher changed after preview", None
                    elif not self._candidate_is_current(row):
                        state, detail, transaction = "Skipped", "Bank ledger amount or bank mapping changed after preview", None
                    else:
                        transaction = frappe.get_doc({
                            "doctype": "Bank Transaction",
                            "date": row.clearance_date,
                            "bank_account": row.bank_account,
                            "company": self.company,
                            "currency": frappe.db.get_value("Account", frappe.db.get_value("Bank Account", row.bank_account, "account"), "account_currency"),
                            "deposit": row.deposit,
                            "withdrawal": row.withdrawal,
                            "reference_number": row.source_document,
                            "description": "Backfill from " + self.name + ": " + self.source_doctype + " " + row.source_document,
                        })
                        transaction.append("payment_entries", {
                            "payment_document": self.source_doctype,
                            "payment_entry": row.source_document,
                            "allocated_amount": 0,
                        })
                        transaction.insert()
                        transaction.submit()
                        state, detail, transaction = "Created", "", transaction.name
            except Exception as exc:
                frappe.db.rollback(save_point=savepoint)
                state, detail, transaction = "Failed", str(exc)[:500], None
                frappe.log_error(title="Bank Transaction Backfill: " + row.source_document, message=frappe.get_traceback())
            counts[state] += 1
            frappe.db.set_value("Bank Transaction Backfill Entry", row.name, {
                "status": state, "error_message": detail, "bank_transaction": transaction,
            }, update_modified=False)
        frappe.db.set_value(self.doctype, self.name, {
            "created_count": counts["Created"], "skipped_count": counts["Skipped"], "failed_count": counts["Failed"],
        }, update_modified=False)

    def before_cancel(self):
        frappe.throw(_("Backfill execution records cannot be cancelled. Create a new backfill for remaining entries."))
