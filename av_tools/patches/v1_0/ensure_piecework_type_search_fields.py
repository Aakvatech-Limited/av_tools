import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


PROPERTY_SETTER_NAME = "Piecework Type-search_fields"


def execute():
    if not frappe.db.exists("DocType", "Piecework Type"):
        return

    if frappe.db.exists("Property Setter", PROPERTY_SETTER_NAME):
        frappe.db.set_value(
            "Property Setter",
            PROPERTY_SETTER_NAME,
            {
                "doc_type": "Piecework Type",
                "field_name": None,
                "property": "search_fields",
                "property_type": "Data",
                "value": "task_name",
            },
        )
        return

    make_property_setter(
        doctype="Piecework Type",
        fieldname=None,
        property="search_fields",
        value="task_name",
        property_type="Data",
        for_doctype=True,
    )
