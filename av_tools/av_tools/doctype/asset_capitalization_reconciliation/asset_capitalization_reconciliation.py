import frappe
from frappe.model.document import Document
from frappe.utils import flt

SOURCE_TYPES = ("Purchase Invoice", "Journal Entry", "Purchase Receipt", "Asset", "Stock Entry")
LINE_FIELDS = {"Purchase Invoice": "items", "Purchase Receipt": "items", "Journal Entry": "accounts"}


class AssetCapitalizationReconciliation(Document):
    def validate(self):
        self.asset_total = sum(flt(row.allocated_amount) for row in self.assets)
        self.source_total = sum(flt(row.allocated_amount) for row in self.sources)
        self.variance = self.asset_total - self.source_total
        for row in self.sources:
            row.reconciliation_purchase_invoice = (
                row.source_voucher if row.source_voucher_type == "Purchase Invoice" else None
            )
            row.reconciliation_journal_entry = (
                row.source_voucher if row.source_voucher_type == "Journal Entry" else None
            )
        if self.status == "Approved":
            if not self.assets or not self.sources or abs(self.variance) > 0.01:
                frappe.throw("Both allocation tables are required and totals must balance within 0.01.")
        for row in self.assets:
            if row.asset:
                self.check_reference("Asset", row.asset)
            if self.status == "Approved" and (not row.asset or not flt(row.allocated_amount)):
                frappe.throw("Asset rows need an Asset and non-zero amount.")
        for row in self.sources:
            if row.source_voucher_type and row.source_voucher_type not in SOURCE_TYPES:
                frappe.throw("Invalid source voucher type.")
            if self.status == "Approved" and (
                not row.source_voucher_type or not row.source_voucher or not flt(row.allocated_amount)
            ):
                frappe.throw("Source rows need Voucher Type, Source Voucher and non-zero amount.")
            if not row.source_voucher_type or not row.source_voucher:
                if row.gl_entry or row.source_line:
                    frappe.throw("Select a source voucher before selecting a GL entry or source line.")
                continue
            voucher = self.check_reference(row.source_voucher_type, row.source_voucher)
            if row.source_line:
                table = LINE_FIELDS.get(row.source_voucher_type)
                if not table or row.source_line not in {line.name for line in voucher.get(table)}:
                    frappe.throw("Source line does not belong to the selected voucher.")
            if row.gl_entry:
                entry = frappe.get_doc("GL Entry", row.gl_entry)
                entry.check_permission("read")
                if (entry.company != self.company or entry.is_cancelled
                    or entry.voucher_type != row.source_voucher_type or entry.voucher_no != row.source_voucher):
                    frappe.throw("GL Entry must be active and belong to the selected company and voucher.")

    def check_reference(self, doctype, name):
        doc = frappe.get_doc(doctype, name)
        doc.check_permission("read")
        if doc.company != self.company:
            frappe.throw("All allocation references must belong to the reconciliation company.")
        if self.status == "Approved" and doc.docstatus != 1:
            frappe.throw("Only submitted documents may be allocated in an Approved reconciliation.")
        return doc
