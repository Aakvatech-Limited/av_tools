import frappe


ROOT_CAUSE_DOCTYPES = (
    "Root Cause Analysis",
    "Possible Root Cause",
    "Root Cause Prevention Strategy",
)


def execute():
    for doctype_name in ROOT_CAUSE_DOCTYPES:
        if frappe.db.exists("DocType", doctype_name):
            frappe.db.set_value("DocType", doctype_name, "module", "Av Tools")
