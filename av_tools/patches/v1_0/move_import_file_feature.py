import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


DOCTYPES = ("Import File",)


def execute():
    for doctype_name in DOCTYPES:
        if frappe.db.exists("DocType", doctype_name):
            frappe.db.set_value("DocType", doctype_name, "module", "Av Tools")

    create_custom_fields(
        {
            "Journal Entry": [
                {
                    "fieldname": "import_file",
                    "fieldtype": "Link",
                    "insert_after": "clearance_date",
                    "label": "Import File",
                    "options": "Import File",
                    "allow_on_submit": 1,
                }
            ],
            "Landed Cost Voucher": [
                {
                    "fieldname": "import_file",
                    "fieldtype": "Link",
                    "insert_after": "sec_break1",
                    "label": "Import File",
                    "options": "Import File",
                }
            ],
            "Purchase Invoice": [
                {
                    "fieldname": "import_file",
                    "fieldtype": "Link",
                    "insert_after": "reference",
                    "label": "Import File",
                    "options": "Import File",
                    "allow_on_submit": 1,
                }
            ],
        },
        update=True,
    )
