import frappe
from frappe import _
from frappe.utils import flt


def validate_payment_allocation(doc, method=None):
	invoice_total = flt(doc.rounded_total or doc.grand_total, doc.precision("grand_total"))
	paid_amount = sum(flt(row.amount, row.precision("amount")) for row in doc.get("payments", []))
	if invoice_total > 0 and flt(paid_amount - invoice_total, doc.precision("grand_total")) > 0:
		frappe.throw(_("Total payment allocation cannot exceed invoice total."))
