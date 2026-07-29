import frappe


MISC_DOCTYPES = (
    "BOM Additional Costs",
    "Inv ERR Detail",
    "Reporting GL Entry",
    "Station Members",
)


def execute():
    for doctype_name in MISC_DOCTYPES:
        if frappe.db.exists("DocType", doctype_name):
            frappe.db.set_value("DocType", doctype_name, "module", "Av Tools")
