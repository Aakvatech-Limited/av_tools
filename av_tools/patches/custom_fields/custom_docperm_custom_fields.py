import json
import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


JSON_FILE = "custom_docperm_custom_fields.json"


def execute():
    json_path = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "custom_fields_json", JSON_FILE
    )
    with open(json_path, "r") as f:
        custom_fields_obj = json.load(f)

    disallowed_fields = [
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "is_system_generated",
        "__last_sync_on",
    ]

    doctype_custom_fields_dict = {}
    for custom_field in custom_fields_obj:
        doctype = custom_field["dt"]
        if not frappe.db.exists("DocType", doctype):
            continue

        all_fields = frappe.get_meta("Custom Field").get_valid_columns()
        field_list = set(all_fields).difference(disallowed_fields)
        custom_field_dict = {
            field_name: custom_field.get(field_name) for field_name in field_list
        }

        doctype_custom_fields_dict.setdefault(doctype, []).append(custom_field_dict)

    create_custom_fields(doctype_custom_fields_dict, update=True)
