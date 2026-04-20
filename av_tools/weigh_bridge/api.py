import frappe
from frappe.utils import flt


ALLOWED_REFERENCE_DOCTYPES = {
    "Sales Invoice",
    "Delivery Note",
    "Sales Order",
    "Purchase Order",
    "Purchase Invoice",
    "Purchase Receipt",
}

ALLOWED_TARGETS_BY_SOURCE = {
    "Sales Order": {"Sales Invoice"},
    "Delivery Note": {"Sales Invoice"},
    "Purchase Order": {"Purchase Invoice"},
    "Purchase Receipt": {"Purchase Invoice"},
}


def _get_settings():
    settings = frappe.get_single("Weighbridge Settings")
    if not settings.enabled:
        frappe.throw("Weighbridge Settings is disabled.")
    if not settings.read_weight_url:
        frappe.throw("Read Weight URL is required in Weighbridge Settings.")
    return settings


@frappe.whitelist()
def read_weight(mode=None):
    settings = _get_settings()
    return {
        "read_weight_url": settings.read_weight_url,
        "mode": mode,
    }


@frappe.whitelist()
def get_gateway_payload():
    settings = _get_settings()
    return {
        "read_weight_url": settings.read_weight_url,
        "timeout_seconds": settings.timeout_seconds,
    }


@frappe.whitelist()
def get_reference_items(document_type=None, document_reference=None):
    if not document_type or not document_reference:
        frappe.throw("Document Type and Document Reference are required.")

    if document_type not in ALLOWED_REFERENCE_DOCTYPES:
        frappe.throw(f"Unsupported reference doctype: {document_type}")

    doc = frappe.get_doc(document_type, document_reference)
    doc.check_permission("read")

    if doc.meta.is_submittable and doc.docstatus == 2:
        frappe.throw(f"{document_type} {document_reference} is Cancelled.")

    items = []
    for row in (doc.get("items") or []):
        if not row.item_code:
            continue
        items.append(
            {
                "item_code": row.item_code,
                "item_name": row.get("item_name"),
                "qty": flt(row.get("qty")),
                "uom": row.get("uom"),
            }
        )

    return {
        "items": items,
        "company": doc.get("company"),
        "customer": doc.get("customer"),
        "supplier": doc.get("supplier"),
    }


@frappe.whitelist()
def get_ticket_items(ticket, doctype=None, document_name=None):
    if not ticket:
        frappe.throw("Weighbridge Ticket is required.")

    doc = frappe.get_doc("Weighbridge Ticket", ticket)
    if doc.docstatus != 1:
        frappe.throw("Weighbridge Ticket must be submitted.")

    is_source_request = (
        doctype
        and document_name
        and doc.document_type == doctype
        and doc.document_reference == document_name
    )

    if doctype and doc.document_type == doctype and not is_source_request:
        frappe.throw(
            f"Cannot use Weighbridge Ticket {doc.name} from {doc.document_type} as target {doctype}."
        )

    if (
        doctype
        and doc.target_document_type
        and doc.target_document_type != doctype
        and not is_source_request
    ):
        frappe.throw("Weighbridge Ticket target document type does not match.")
    if (
        document_name
        and doc.target_document_reference
        and doc.target_document_reference != document_name
        and not is_source_request
    ):
        frappe.throw("Weighbridge Ticket belongs to another document.")

    if (
        document_name
        and doctype
        and frappe.db.exists(doctype, document_name)
        and not is_source_request
    ):
        if doc.document_type:
            allowed_targets = ALLOWED_TARGETS_BY_SOURCE.get(doc.document_type, set())
            if doctype not in allowed_targets:
                frappe.throw(
                    f"Weighbridge source {doc.document_type} can only create: {', '.join(sorted(allowed_targets)) or 'None'}."
                )

        frappe.db.set_value(
            "Weighbridge Ticket",
            doc.name,
            {
                "target_document_type": doctype,
                "target_document_reference": document_name,
            },
            update_modified=True,
        )
        doc.target_document_type = doctype
        doc.target_document_reference = document_name

    items = [
        {
            "item_code": row.item_code,
            "item_name": row.item_name,
            "qty": row.qty,
            "uom": row.uom,
        }
        for row in (doc.items or [])
    ]

    return {
        "items": items,
        "document_type": doc.document_type,
        "document_reference": doc.document_reference,
        "target_document_type": doc.target_document_type,
        "target_document_reference": doc.target_document_reference,
        "company": doc.company,
        "customer": doc.customer,
        "supplier": doc.supplier,
        "posting_date": doc.posting_date,
        "posting_time": doc.posting_time,
        "tare_weight": doc.tare_weight,
        "gross_weight": doc.gross_weight,
        "net_weight": doc.net_weight,
    }
