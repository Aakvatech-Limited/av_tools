"""Audit role permission changes, with one row per Permission Log."""

import json

import frappe
from frappe.utils import add_days, add_months, get_first_day, get_last_day, getdate, today

PERMISSION_FIELDS = (
    "select", "read", "write", "create", "delete", "submit",
    "cancel", "amend", "report", "export", "import", "share",
    "print", "email", "mask", "impersonate", "if_owner",
)
ENABLED = (1, True, "1", "true", "True")


def execute(filters=None):
    # Permission Log contains security-sensitive changes, so check server-side.
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Only System Managers can review permission audit history.", frappe.PermissionError)

    filters = frappe._dict(filters or {})
    span = filters.get("time_span") or "Last 7 Days"
    current = today()
    start = current
    end = current
    if span == "Yesterday":
        start = end = add_days(current, -1)
    elif span == "This Week":
        start = add_days(current, -getdate(current).weekday())
        end = add_days(start, 6)
    elif span == "Last Week":
        week_start = add_days(current, -getdate(current).weekday())
        start, end = add_days(week_start, -7), add_days(week_start, -1)
    elif span == "Last 7 Days":
        start = add_days(current, -6)
    elif span == "This Month":
        start, end = get_first_day(current), get_last_day(current)
    elif span == "Last Month":
        last_month = add_months(current, -1)
        start, end = get_first_day(last_month), get_last_day(last_month)
    elif span == "Period":
        if not filters.get("from_date") or not filters.get("to_date"):
            frappe.throw("From Date and To Date are required for Period.")
        start, end = filters.from_date, filters.to_date
    else:
        frappe.throw("Invalid Time Span.")

    if getdate(start) > getdate(end):
        frappe.throw("From Date cannot be after To Date.")

    columns = [
        {"label": "Changed At", "fieldname": "changed_at", "fieldtype": "Datetime", "width": 170},
        {"label": "DocType", "fieldname": "target_doctype", "fieldtype": "Link", "options": "DocType", "width": 200},
        {"label": "Role", "fieldname": "role", "fieldtype": "Link", "options": "Role", "width": 155},
        {"label": "Perm Level", "fieldname": "permlevel", "fieldtype": "Int", "width": 90},
        {"label": "Action", "fieldname": "action", "fieldtype": "Data", "width": 95},
        {"label": "Changed By", "fieldname": "changed_by", "fieldtype": "Link", "options": "User", "width": 190},
    ]
    columns.extend(
        {"label": field.replace("_", " ").title(), "fieldname": field, "fieldtype": "Data", "width": 105}
        for field in PERMISSION_FIELDS
    )
    columns.append(
        {"label": "Permission Log", "fieldname": "permission_log", "fieldtype": "Link", "options": "Permission Log", "width": 145}
    )

    Log = frappe.qb.DocType("Permission Log")
    query = (
        frappe.qb.from_(Log)
        .select(
            Log.name, Log.creation, Log.owner, Log.status,
            Log.for_document, Log.reference_type, Log.reference, Log.changes
        )
        .where(Log.creation >= str(start) + " 00:00:00")
        .where(Log.creation < str(add_days(end, 1)) + " 00:00:00")
        .where(Log.reference_type.isin(["Custom DocPerm", "DocPerm"]))
    )
    if filters.get("doctype_name"):
        query = query.where(Log.for_document == filters.doctype_name)
    if filters.get("changed_by"):
        query = query.where(Log.owner == filters.changed_by)
    logs = query.orderby(Log.creation).run(as_dict=True)

    # Batched identity lookup avoids one query per log.
    references = {"Custom DocPerm": set(), "DocPerm": set()}
    for log in logs:
        if log.reference and log.reference_type in references:
            references[log.reference_type].add(log.reference)

    identity = {}
    for kind, names in references.items():
        if not names:
            continue
        Perm = frappe.qb.DocType(kind)
        for item in (
            frappe.qb.from_(Perm)
            .select(Perm.name, Perm.role, Perm.permlevel)
            .where(Perm.name.isin(list(names)))
            .run(as_dict=True)
        ):
            identity[(kind, item.name)] = item

    result = []
    for log in logs:
        if not log.changes:
            continue
        try:
            changes = json.loads(log.changes) if isinstance(log.changes, str) else log.changes
        except (ValueError, TypeError) as exc:
            frappe.throw("Invalid JSON in Permission Log " + log.name + ": " + str(exc))
        if not isinstance(changes, dict):
            continue
        old_values = changes.get("from") or {}
        new_values = changes.get("to") or {}
        if not isinstance(old_values, dict) or not isinstance(new_values, dict):
            continue

        current_perm = identity.get((log.reference_type, log.reference))
        role = (current_perm.role if current_perm else None)
        level = (current_perm.permlevel if current_perm else None)
        # Historical values take precedence when included in the log.
        if "role" in new_values:
            role = new_values["role"]
        elif "role" in old_values:
            role = old_values["role"]
        if "permlevel" in new_values:
            level = new_values["permlevel"]
        elif "permlevel" in old_values:
            level = old_values["permlevel"]
        if filters.get("role") and filters.role != role:
            continue

        status = str(log.status or "Updated")
        state = status.lower()
        created = state in ("created", "added", "inserted")
        deleted = state in ("deleted", "removed")
        row = {
            "changed_at": log.creation, "target_doctype": log.for_document,
            "role": role, "permlevel": level, "action": status,
            "changed_by": log.owner, "permission_log": log.name,
        }
        for field in PERMISSION_FIELDS:
            row[field] = ""

        for field in PERMISSION_FIELDS:
            old_present, new_present = field in old_values, field in new_values
            old_on = old_values.get(field) in ENABLED
            new_on = new_values.get(field) in ENABLED
            if created and new_present and new_on:
                row[field] = "Added"
            elif deleted and old_present and old_on:
                row[field] = "Removed"
            elif old_present and new_present and old_on != new_on:
                row[field] = "Added" if new_on else "Removed"
            # If only one state exists on an Update log, do not invent the other state.

        changed = [row[field] for field in PERMISSION_FIELDS if row[field]]
        if not changed:
            continue
        if filters.get("permission") and not row.get(filters.permission):
            continue
        action_filter = filters.get("action")
        if action_filter and action_filter != "All":
            if action_filter in ("Added", "Removed"):
                if action_filter not in changed:
                    continue
            elif state != action_filter.lower():
                continue
        result.append(row)

    result.reverse()
    return columns, result
