import json
import os

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


JSON_FILE = "property_setter.json"


def execute():
    json_path = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "property_setter_json", JSON_FILE
    )
    with open(json_path, "r") as f:
        property_setters_obj = json.load(f)

    for property_setter in property_setters_obj:
        doc_type = property_setter.get("doc_type")
        if not doc_type or not frappe.db.exists("DocType", doc_type):
            continue

        for_doctype = property_setter.get("doctype_or_field") == "DocType"

        make_property_setter(
            doctype=doc_type,
            fieldname=property_setter.get("field_name"),
            property=property_setter.get("property"),
            value=property_setter.get("value"),
            property_type=property_setter.get("property_type"),
            for_doctype=for_doctype,
            validate_fields_for_doctype=False,
        )
