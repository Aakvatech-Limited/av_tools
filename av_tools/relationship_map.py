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


def _links_for(doctype, name):
    """Look up both parent Link fields and child-table Link fields.

    Candidate SQL is restricted to known transaction DocTypes, and every candidate
    is checked for document read permission before it reaches the client.
    """
    edges = set()
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
