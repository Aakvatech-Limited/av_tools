import frappe
from frappe import _
from frappe.utils import flt


def validate_payment_allocation(doc, method=None):
	if not doc.is_pos:
		return

	invoice_total = flt(doc.rounded_total or doc.grand_total, doc.precision("grand_total"))
	if invoice_total <= 0:
		return

	payment_total = sum(flt(row.amount, row.precision("amount")) for row in doc.get("payments", []))
	remaining = flt(invoice_total - payment_total, doc.precision("grand_total"))
	# In POS, cashier may collect more than the invoice total; the excess is change returned to customer.
	if remaining < 0 and not doc.is_pos:
		frappe.throw(_("Total payment allocation cannot exceed invoice total."))

	doc.remaining_balance = max(remaining, 0)
