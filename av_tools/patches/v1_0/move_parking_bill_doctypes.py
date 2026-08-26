import frappe


PARKING_BILL_DOCTYPES = (
    "Parking Bill",
    "Parking Bill Details",
    "Parking Bill Items",
)


def execute():
    for doctype_name in PARKING_BILL_DOCTYPES:
        if frappe.db.exists("DocType", doctype_name):
            frappe.db.set_value("DocType", doctype_name, "module", "Av Tools")
