import frappe
from frappe.utils import flt


def _get_qty_by_item(rows):
	qty_by_item = {}
	for row in rows or []:
		item_code = (row.get("item_code") or "").strip()
		if not item_code:
			continue
		qty_by_item[item_code] = qty_by_item.get(item_code, 0) + flt(row.get("qty"))
	return qty_by_item


def validate_weighbridge_ticket(doc, method=None):
	"""Validate ticket-controlled item rows without restricting other document items."""
	header_ticket = doc.get("weighbridge_ticket")
	linked_rows = [row for row in doc.get("items") or [] if row.get("weighbridge_ticket")]
	ticket_names = {row.get("weighbridge_ticket") for row in linked_rows}
	if header_ticket:
		ticket_names.add(header_ticket)
	if not ticket_names:
		return

	for ticket_name in ticket_names:
		ticket = frappe.get_doc("Weighbridge Ticket", ticket_name)
		if ticket.docstatus != 1:
			frappe.throw(f"Weighbridge Ticket {ticket_name} must be submitted.")

		is_source_doc = (
			ticket.get("document_type") == doc.doctype
			and ticket.get("document_reference") == doc.name
		)
		if ticket.get("document_type") == doc.doctype and not is_source_doc:
			frappe.throw(
				f"Cannot use Weighbridge Ticket {ticket_name} from {ticket.document_type} as target {doc.doctype}."
			)
		if ticket.get("target_document_type") and not is_source_doc:
			if ticket.target_document_type != doc.doctype:
				frappe.throw(f"Weighbridge Ticket {ticket_name} has a different target document type.")
		if (
			not doc.get("__islocal")
			and ticket.get("target_document_type") == doc.doctype
			and ticket.get("target_document_reference")
			and ticket.target_document_reference != doc.name
		):
			frappe.throw(f"Weighbridge Ticket {ticket_name} belongs to another document.")

		# A header ticket is contextual. Only items carrying a ticket link
		# represent goods controlled by that ticket.
		rows = [row for row in linked_rows if row.get("weighbridge_ticket") == ticket_name]
		if not rows or is_source_doc:
			continue

		ticket_qty = _get_qty_by_item(ticket.get("items"))
		used_qty = {}
		for row in rows:
			code = (row.get("item_code") or "").strip()
			if code not in ticket_qty:
				frappe.throw(
					f"Row {row.idx}: {code or 'Item'} is not in Weighbridge Ticket {ticket_name}."
				)
			used_qty[code] = used_qty.get(code, 0) + flt(row.get("qty"))

		for code, qty in used_qty.items():
			if qty > ticket_qty[code] + 1e-9:
				frappe.throw(
					f"Weighbridge Ticket {ticket_name}: {code} quantity {qty} exceeds ticket quantity {ticket_qty[code]}."
				)
