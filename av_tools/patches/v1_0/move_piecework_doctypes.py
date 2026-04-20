import frappe


PIECEWORK_DOCTYPES = (
    "Piecework",
    "Piecework Single",
    "Piecework Type",
    "Piecework Payment Allocation",
    "Piecework Salary Disbursement",
    "Employee Piecework Additional Salary",
    "Single Piecework Employees",
)


def execute():
    for doctype_name in PIECEWORK_DOCTYPES:
        if frappe.db.exists("DocType", doctype_name):
            frappe.db.set_value("DocType", doctype_name, "module", "Av Tools")
