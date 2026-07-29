import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def setup_custom_fields():
    custom_fields = {
        "Vehicle": [
            {
                "fieldname": "default_tare_weight",
                "label": "Default Tare Weight",
                "fieldtype": "Float",
                "insert_after": "license_plate",
            }
        ],
        "Sales Invoice": [
            {
                "fieldname": "weighbridge_ticket",
                "label": "Weighbridge Ticket",
                "fieldtype": "Link",
                "options": "Weighbridge Ticket",
                "insert_after": "company",
            }
        ],
        "Delivery Note": [
            {
                "fieldname": "weighbridge_ticket",
                "label": "Weighbridge Ticket",
                "fieldtype": "Link",
                "options": "Weighbridge Ticket",
                "insert_after": "company",
            }
        ],
        "Sales Order": [
            {
                "fieldname": "weighbridge_ticket",
                "label": "Weighbridge Ticket",
                "fieldtype": "Link",
                "options": "Weighbridge Ticket",
                "insert_after": "company",
            }
        ],
        "Purchase Invoice": [
            {
                "fieldname": "weighbridge_ticket",
                "label": "Weighbridge Ticket",
                "fieldtype": "Link",
                "options": "Weighbridge Ticket",
                "insert_after": "supplier",
            }
        ],
        "Purchase Order": [
            {
                "fieldname": "weighbridge_ticket",
                "label": "Weighbridge Ticket",
                "fieldtype": "Link",
                "options": "Weighbridge Ticket",
                "insert_after": "supplier",
            }
        ],
        "Purchase Receipt": [
            {
                "fieldname": "weighbridge_ticket",
                "label": "Weighbridge Ticket",
                "fieldtype": "Link",
                "options": "Weighbridge Ticket",
                "insert_after": "supplier",
            }
        ],
    }

    create_custom_fields(custom_fields, update=True)
