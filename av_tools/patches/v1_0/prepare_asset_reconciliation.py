"""Adopt custom DocTypes in place before model sync; never rename/drop their tables."""

import frappe
from frappe.permissions import setup_custom_perms

DOCTYPES = (
    "Asset Reconciliation Asset",
    "Asset Reconciliation Source",
    "Asset Capitalization Reconciliation",
)


def execute():
    report = "Fixed Asset Financial Reconciliation"
    if (frappe.db.exists("Report", report)
        and frappe.db.get_value("Report", report, "is_standard") == "No"
        and not frappe.db.exists("Custom Role", {"report": report})):
        roles = frappe.get_all("Has Role", filters={"parent": report, "parenttype": "Report"}, pluck="role")
        if roles:
            frappe.get_doc({"doctype": "Custom Role", "report": report,
                            "roles": [{"role": role} for role in roles]}).insert(ignore_permissions=True)
    for name in DOCTYPES:
        if frappe.db.exists("DocType", name):
            if frappe.db.get_value("DocType", name, "custom") and name == "Asset Capitalization Reconciliation":
                # Retain site-specific role permissions when standard DocPerm syncs.
                setup_custom_perms(name)
            frappe.db.set_value("DocType", name, {"module": "Av Tools", "custom": 0}, update_modified=False)
            frappe.clear_cache(doctype=name)
