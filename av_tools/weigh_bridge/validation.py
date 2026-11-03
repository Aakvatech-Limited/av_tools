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



def _is_sales_order_item(row):
	"""Allow document items that can be traced to an actual Sales Order item."""
	sales_order = row.get("sales_order")
	item_code = (row.get("item_code") or "").strip()
	if not sales_order or not item_code:
		return False

	filters = {"parent": sales_order, "item_code": item_code}
	if row.get("so_detail"):
		filters["name"] = row.get("so_detail")
	return bool(frappe.db.exists("Sales Order Item", filters))


def validate_weighbridge_ticket(doc, method=None):
	ticket_name = doc.get("weighbridge_ticket")
	if not ticket_name:
		return

	ticket = frappe.get_doc("Weighbridge Ticket", ticket_name)
	if ticket.docstatus != 1:
		frappe.throw("Weighbridge Ticket must be submitted.")

	is_source_doc = (
		ticket.get("document_type") == doc.doctype and ticket.get("document_reference") == doc.name
	)
	is_target_doctype = ticket.get("target_document_type") == doc.doctype

	if ticket.get("document_type") == doc.doctype and not is_source_doc:
		frappe.throw(
			f"Cannot use Weighbridge Ticket {ticket.name} from {ticket.document_type} as target {doc.doctype}."
		)

	if (
		not doc.get("__islocal")
		and is_target_doctype
		and ticket.get("target_document_reference")
		and ticket.target_document_reference != doc.name
	):
		frappe.throw("Weighbridge Ticket belongs to another document.")

	# In source->ticket->target flows, source docs can keep their own qty/items.
	# Exact item/qty enforcement applies on the target document.
	if ticket.get("target_document_type") and is_source_doc and not is_target_doctype:
		return

	ticket_qty_by_item = _get_qty_by_item(ticket.get("items"))
	doc_qty_by_item = _get_qty_by_item(doc.get("items"))

	extra_items = sorted({
		(row.get("item_code") or "").strip()
		for row in doc.get("items") or []
		if (row.get("item_code") or "").strip() not in ticket_qty_by_item
		and (row.get("item_code") or "").strip()
		and not _is_sales_order_item(row)
	})
	if extra_items:
		frappe.throw(f"Items not in Weighbridge Ticket: {', '.join(extra_items)}")

	missing_items = sorted([item for item in ticket_qty_by_item if item not in doc_qty_by_item])
	if missing_items:
		frappe.throw(f"Items missing from document: {', '.join(missing_items)}")

	qty_mismatch = []
	for item_code, ticket_qty in ticket_qty_by_item.items():
		doc_qty = flt(doc_qty_by_item.get(item_code))
		ticket_qty = flt(ticket_qty)
		if abs(doc_qty - ticket_qty) > 1e-9:
			qty_mismatch.append(f"{item_code} ({doc_qty} != {ticket_qty})")

	if qty_mismatch:
		frappe.throw(f"Qty must match Weighbridge Ticket: {', '.join(qty_mismatch)}")
