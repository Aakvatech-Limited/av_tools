"""Read-only, permission-filtered ERPNext transaction relationship map."""

from collections import deque

import frappe
from frappe import _

SUPPORTED = (
    "Material Request", "Request for Quotation", "Supplier Quotation",
    "Purchase Order", "Purchase Receipt", "Purchase Invoice",
    "Quotation", "Sales Order", "Delivery Note", "Sales Invoice",
    "Stock Entry", "Stock Reconciliation", "Payment Entry",
    "Payment Request", "Journal Entry",
)
MAX_NODES = 60
MAX_DEPTH = 3
MAX_CANDIDATES = 150


def _visible(doctype, name):
    return frappe.has_permission(doctype, "read", doc=name)


def _summary(doctype, name):
    doc = frappe.get_doc(doctype, name)
    if not _visible(doctype, name):
        return None
    status = doc.get("status") if doc.meta.has_field("status") else None
    return {
        "id": doctype + "::" + name,
        "doctype": doctype,
        "name": name,
        "docstatus": doc.docstatus,
        "status": status,
        "workflow_state": doc.get("workflow_state") if doc.meta.has_field("workflow_state") else None,
        "posting_date": str(doc.get("posting_date") or doc.get("transaction_date") or doc.get("date") or ""),
        "currency": doc.get("currency") if doc.meta.has_field("currency") else None,
        "amount": str(
            doc.get("grand_total") or doc.get("paid_amount") or doc.get("total_amount")
            or doc.get("base_grand_total") or ""
        ),
        "created_by": doc.owner,
        "created_at": str(doc.creation),
        "modified_by": doc.modified_by,
        "modified_at": str(doc.modified),
        # modified_by is never presented as the approving/submitting user.
        "authorization": _authorization(doctype, name),
    }


def _authorization(doctype, name):
    """A Version entry is only evidence if it explicitly records a docstatus change."""
    if not frappe.has_permission("Version", "read"):
        return None
    versions = frappe.get_all(
        "Version",
        filters={"ref_doctype": doctype, "docname": name},
        fields=["data", "owner", "creation"],
        order_by="creation desc",
        limit_page_length=100,
    )
    for version in versions:
        try:
            data = frappe.parse_json(version.data)
            for change in data.get("changed", []):
                if len(change) >= 3 and change[0] == "docstatus" and str(change[2]) == "1":
                    return {"by": version.owner, "at": str(version.creation), "source": "Version"}
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return None


def _dynamic_references(doctype, name):
    """Find references that use (reference_doctype, reference_name) pairs."""
    edges = set()
    # These are actual ERPNext dynamic-reference pairs, not regular Link fields.
    for parent, child, table_field in (
        ("Payment Entry", "Payment Entry Reference", "references"),
        ("Journal Entry", "Journal Entry Account", "accounts"),
    ):
        if parent not in SUPPORTED or not frappe.db.exists("DocType", child):
            continue
        meta = frappe.get_meta(child)
        if not meta.has_field("reference_type") and not meta.has_field("reference_doctype"):
            continue
        type_field = "reference_doctype" if meta.has_field("reference_doctype") else "reference_type"
        if not meta.has_field("reference_name"):
            continue
        rows = frappe.get_all(
            child,
            filters={"parenttype": parent, "parentfield": table_field,
                     type_field: doctype, "reference_name": name},
            fields=["parent"],
            limit_page_length=MAX_CANDIDATES,
        )
        for row in rows:
            edges.add((doctype, name, parent, row.parent))
    # Payment Request stores the same pair on its parent document.
    if frappe.db.exists("DocType", "Payment Request"):
        meta = frappe.get_meta("Payment Request")
        if meta.has_field("reference_doctype") and meta.has_field("reference_name"):
            for target in frappe.get_all(
                "Payment Request",
                filters={"reference_doctype": doctype, "reference_name": name},
                pluck="name", limit_page_length=MAX_CANDIDATES,
            ):
                edges.add((doctype, name, "Payment Request", target))
    return edges


def _source_dynamic_references(doc):
    """Resolve outbound dynamic references from the current document."""
    edges = set()
    if doc.doctype == "Payment Entry":
        for ref in doc.get("references") or []:
            if ref.reference_doctype in SUPPORTED and ref.reference_name:
                edges.add((ref.reference_doctype, ref.reference_name, doc.doctype, doc.name))
    elif doc.doctype == "Journal Entry":
        for ref in doc.get("accounts") or []:
            if ref.reference_type in SUPPORTED and ref.reference_name:
                edges.add((ref.reference_type, ref.reference_name, doc.doctype, doc.name))
    elif doc.doctype == "Payment Request":
        if doc.get("reference_doctype") in SUPPORTED and doc.get("reference_name"):
            edges.add((doc.reference_doctype, doc.reference_name, doc.doctype, doc.name))
    return edges


# Source child item -> target child item references not surfaced by parent Link fields.
ITEM_REFERENCES = (
    ("Delivery Note", "Delivery Note Item", "Sales Invoice", "Sales Invoice Item", "dn_detail"),
    ("Purchase Receipt", "Purchase Receipt Item", "Purchase Invoice", "Purchase Invoice Item", "pr_detail"),
    ("Sales Order", "Sales Order Item", "Delivery Note", "Delivery Note Item", "so_detail"),
    ("Sales Order", "Sales Order Item", "Sales Invoice", "Sales Invoice Item", "so_detail"),
    ("Purchase Order", "Purchase Order Item", "Purchase Receipt", "Purchase Receipt Item", "po_detail"),
    ("Purchase Order", "Purchase Order Item", "Purchase Invoice", "Purchase Invoice Item", "po_detail"),
)


def _item_references(doctype, name):
    """Resolve cross-document item references through source child-row identifiers."""
    edges = set()
    for source, source_child, target, target_child, fieldname in ITEM_REFERENCES:
        if doctype not in (source, target):
            continue
        if not frappe.db.exists("DocType", source_child) or not frappe.db.exists("DocType", target_child):
            continue
        if not frappe.get_meta(target_child).has_field(fieldname):
            continue
        if doctype == source:
            ids = frappe.get_all(
                source_child, filters={"parenttype": source, "parent": name},
                pluck="name", limit_page_length=MAX_CANDIDATES,
            )
            if not ids:
                continue
            rows = frappe.get_all(
                target_child,
                filters={"parenttype": target, fieldname: ("in", ids)},
                fields=["parent"], limit_page_length=MAX_CANDIDATES,
            )
            for row in rows:
                edges.add((source, name, target, row.parent))
        else:
            references = frappe.get_all(
                target_child,
                filters={"parenttype": target, "parent": name},
                fields=[fieldname], limit_page_length=MAX_CANDIDATES,
            )
            ids = [row.get(fieldname) for row in references if row.get(fieldname)]
            if not ids:
                continue
            rows = frappe.get_all(
                source_child,
                filters={"parenttype": source, "name": ("in", ids)},
                fields=["parent"], limit_page_length=MAX_CANDIDATES,
            )
            for row in rows:
                edges.add((source, row.parent, target, name))
    return edges


def _links_for(doctype, name):
    """Look up both parent Link fields and child-table Link fields.

    Candidate SQL is restricted to known transaction DocTypes, and every candidate
    is checked for document read permission before it reaches the client.
    """
    edges = _dynamic_references(doctype, name)
    edges.update(_item_references(doctype, name))
    for other in SUPPORTED:
        if not frappe.db.exists("DocType", other):
            continue
        meta = frappe.get_meta(other)
        for df in meta.fields:
            if df.fieldtype == "Link" and df.options == doctype:
                candidates = frappe.get_all(
                    other,
                    filters={df.fieldname: name},
                    pluck="name",
                    limit_page_length=MAX_CANDIDATES,
                )
                for candidate in candidates:
                    edges.add((doctype, name, other, candidate))
            elif df.fieldtype == "Table" and df.options and frappe.db.exists("DocType", df.options):
                child_meta = frappe.get_meta(df.options)
                for link in child_meta.fields:
                    if link.fieldtype != "Link" or link.options != doctype:
                        continue
                    # Child rows cannot be treated as permission-bearing documents.
                    rows = frappe.get_all(
                        df.options,
                        filters={link.fieldname: name, "parenttype": other},
                        fields=["parent"],
                        limit_page_length=MAX_CANDIDATES,
                    )
                    for row in rows:
                        edges.add((doctype, name, other, row.parent))
        # Also locate links from the current document toward its predecessors.
    doc = frappe.get_doc(doctype, name)
    edges.update(_source_dynamic_references(doc))
    for df in doc.meta.fields:
        if df.fieldtype == "Link" and df.options in SUPPORTED:
            target = doc.get(df.fieldname)
            if target:
                edges.add((df.options, target, doctype, name))
        elif df.fieldtype == "Table" and df.options:
            child_meta = frappe.get_meta(df.options)
            for link in child_meta.fields:
                if link.fieldtype not in ("Link",) or link.options not in SUPPORTED:
                    continue
                for row in doc.get(df.fieldname) or []:
                    target = row.get(link.fieldname)
                    if target:
                        edges.add((link.options, target, doctype, name))
    return edges


@frappe.whitelist()
def get_relationship_map(doctype, name):
    if doctype not in SUPPORTED:
        frappe.throw(_("Relationship Map is not supported for this DocType"))
    if not name or not frappe.db.exists(doctype, name):
        frappe.throw(_("Document not found"))
    if not _visible(doctype, name):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    root = doctype + "::" + name
    nodes = {}
    edges = set()
    queue = deque([(doctype, name, 0)])
    explored = set()
    truncated = False
    while queue:
        current_type, current_name, depth = queue.popleft()
        key = current_type + "::" + current_name
        if key in explored:
            continue
        explored.add(key)
        if not frappe.db.exists(current_type, current_name) or not _visible(current_type, current_name):
            continue
        if len(nodes) >= MAX_NODES:
            truncated = True
            break
        nodes[key] = _summary(current_type, current_name)
        if depth >= MAX_DEPTH:
            continue
        for source_type, source_name, target_type, target_name in _links_for(current_type, current_name):
            if source_type not in SUPPORTED or target_type not in SUPPORTED:
                continue
            if not frappe.db.exists(source_type, source_name) or not frappe.db.exists(target_type, target_name):
                continue
            if not _visible(source_type, source_name) or not _visible(target_type, target_name):
                continue
            source = source_type + "::" + source_name
            target = target_type + "::" + target_name
            edges.add((source, target))
            for next_type, next_name in ((source_type, source_name), (target_type, target_name)):
                if next_type + "::" + next_name not in explored:
                    queue.append((next_type, next_name, depth + 1))
    return {
        "root": root,
        "nodes": list(nodes.values()),
        "edges": [{"source": a, "target": b} for a, b in sorted(edges) if a in nodes and b in nodes],
        "truncated": truncated,
    }
