# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now

SNAPSHOT_TABLE = "table_qvkt"
JSON_TABLE = "table_ldiu"

COMMON_AUDIT_FIELDS = ["modified", "modified_by", "owner"]


SECTION_DEFINITIONS = [
    {
        "label": "Client Script",
        "doctype": "Client Script",
        "fields": ["name", "dt", "view", "enabled", "script", *COMMON_AUDIT_FIELDS],
        "order_by": "dt asc, name asc",
    },
    {
        "label": "Server Script",
        "doctype": "Server Script",
        "fields": [
            "name",
            "script_type",
            "reference_doctype",
            "event_frequency",
            "api_method",
            "disabled",
            "script",
            *COMMON_AUDIT_FIELDS,
        ],
        "order_by": "script_type asc, name asc",
    },
    {
        "label": "Custom Field",
        "doctype": "Custom Field",
        "fields": [
            "name",
            "dt",
            "fieldname",
            "label",
            "fieldtype",
            "options",
            "insert_after",
            "reqd",
            "read_only",
            "hidden",
            "depends_on",
            "mandatory_depends_on",
            *COMMON_AUDIT_FIELDS,
        ],
        "order_by": "dt asc, fieldname asc",
    },
    {
        "label": "Property Setter",
        "doctype": "Property Setter",
        "fields": [
            "name",
            "doc_type",
            "field_name",
            "property",
            "property_type",
            "value",
            "default_value",
            *COMMON_AUDIT_FIELDS,
        ],
        "order_by": "doc_type asc, field_name asc, property asc",
    },
    {
        "label": "Workflow",
        "doctype": "Workflow",
        "fields": ["name", "document_type", "is_active", "workflow_state_field", *COMMON_AUDIT_FIELDS],
        "order_by": "document_type asc, name asc",
    },
    {
        "label": "Workflow State",
        "doctype": "Workflow State",
        "fields": ["name", "workflow_state_name", "style", *COMMON_AUDIT_FIELDS],
        "order_by": "workflow_state_name asc",
    },
    {
        "label": "Workflow Action",
        "doctype": "Workflow Action Master",
        "fields": ["name", "workflow_action_name", *COMMON_AUDIT_FIELDS],
        "order_by": "workflow_action_name asc",
    },
    {
        "label": "Print Format",
        "doctype": "Print Format",
        "fields": ["name", "doc_type", "print_format_type", "standard", "disabled", "html", "css", *COMMON_AUDIT_FIELDS],
        "filters": {"standard": "No"},
        "order_by": "doc_type asc, name asc",
    },
    {
        "label": "Report",
        "doctype": "Report",
        "fields": [
            "name",
            "ref_doctype",
            "report_type",
            "is_standard",
            "disabled",
            "json",
            "query",
            "script",
            *COMMON_AUDIT_FIELDS,
        ],
        "filters": {"is_standard": "No"},
        "order_by": "ref_doctype asc, name asc",
    },
    {
        "label": "Dashboard",
        "doctype": "Dashboard",
        "fields": ["name", "is_standard", "module", *COMMON_AUDIT_FIELDS],
        "filters": {"is_standard": 0},
        "order_by": "name asc",
    },
    {
        "label": "Notification",
        "doctype": "Notification",
        "fields": ["name", "document_type", "event", "enabled", "condition", "subject", "message", *COMMON_AUDIT_FIELDS],
        "order_by": "document_type asc, name asc",
    },
    {
        "label": "Web Form",
        "doctype": "Web Form",
        "fields": ["name", "title", "doc_type", "route", "published", "login_required", *COMMON_AUDIT_FIELDS],
        "order_by": "doc_type asc, name asc",
    },
    {
        "label": "Custom Permission",
        "doctype": "Custom DocPerm",
        "fields": [
            "name",
            "parent",
            "role",
            "permlevel",
            "read",
            "write",
            "create",
            "delete",
            "submit",
            "cancel",
            "amend",
            *COMMON_AUDIT_FIELDS,
        ],
        "order_by": "parent asc, role asc, permlevel asc",
    },
    {
        "label": "Custom DocType",
        "doctype": "DocType",
        "fields": ["name", "module", "custom", "istable", "issingle", "is_submittable", "autoname", *COMMON_AUDIT_FIELDS],
        "filters": {"custom": 1},
        "order_by": "name asc",
    },
]

SECTION_BY_LABEL = {section["label"]: section for section in SECTION_DEFINITIONS}


class ImplementationHandoverSnapshot(Document):
    def before_insert(self):
        if not self.site_name:
            self.site_name = frappe.local.site

    def validate(self):
        validate_date_range(self)

    @frappe.whitelist()
    def generate_snapshot(self):
        validate_date_range(self)

        self.site_name = frappe.local.site
        self.generated_on = now()
        self.generated_by = frappe.session.user

        self.set(JSON_TABLE, [])
        for section in build_customization_snapshot(self):
            self.append(
                JSON_TABLE,
                {
                    "type": section["label"],
                    "json_type": dump_json(section["records"]),
                },
            )

        self.save()

        response = {
            "name": self.name,
            "generated_on": self.generated_on,
            "generated_by": self.generated_by,
            "site_name": self.site_name,
            JSON_TABLE: [row.as_dict() for row in self.get(JSON_TABLE)],
        }

        return response


@frappe.whitelist()
def get_snapshot_section_options():
    return [section["label"] for section in SECTION_DEFINITIONS]


def build_customization_snapshot(doc=None):
    sections = []

    for label in get_selected_sections(doc):
        section = SECTION_BY_LABEL.get(label)
        if not section:
            continue

        sections.append(
            {
                "label": section["label"],
                "records": get_section_records(section, doc),
            }
        )

    return sections


def dump_json(value):
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def get_selected_sections(doc):
    if not doc:
        return [section["label"] for section in SECTION_DEFINITIONS]

    seen = set()
    selected = []
    for row in doc.get(SNAPSHOT_TABLE):
        label = row.get("reference")
        if label and label not in seen:
            selected.append(label)
            seen.add(label)

    return selected or [section["label"] for section in SECTION_DEFINITIONS]


def get_section_records(section, doc=None):
    filters = dict(section.get("filters") or {})
    filters.update(get_date_filters(doc, section["doctype"]))

    return get_records(
        section["doctype"],
        section["fields"],
        filters=filters,
        order_by=section.get("order_by"),
    )


def get_date_filters(doc, doctype):
    if not doc or not frappe.db.has_column(doctype, "modified"):
        return {}

    from_date = doc.get("from_date")
    to_date = doc.get("to_date")
    if from_date and to_date:
        return {"modified": ["between", [start_of_day(from_date), end_of_day(to_date)]]}
    if from_date:
        return {"modified": [">=", start_of_day(from_date)]}
    if to_date:
        return {"modified": ["<=", end_of_day(to_date)]}

    return {}


def validate_date_range(doc):
    if doc.get("from_date") and doc.get("to_date") and getdate(doc.from_date) > getdate(doc.to_date):
        frappe.throw("From Date cannot be after To Date")


def start_of_day(date):
    return f"{getdate(date)} 00:00:00"


def end_of_day(date):
    return f"{getdate(date)} 23:59:59"


def get_records(doctype, fields, filters=None, order_by=None):
    if not frappe.db.exists("DocType", doctype):
        return []

    fields = [field for field in fields if frappe.db.has_column(doctype, field)]
    if not fields:
        return []

    return frappe.get_all(
        doctype,
        fields=fields,
        filters=filters,
        order_by=order_by,
    )
