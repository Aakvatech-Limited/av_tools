import frappe
from frappe.utils import cint


def execute():
    _migrate_setting_value()
    _delete_legacy_custom_fields()


def _migrate_setting_value():
    legacy_value = frappe.db.sql(
        """
        SELECT value FROM tabSingles
        WHERE doctype = %s AND field = %s
        LIMIT 1
        """,
        ("CSF TZ Settings", "enable_dependent_auto_permission"),
    )
    legacy_value = legacy_value[0][0] if legacy_value else None

    current_value = frappe.db.get_single_value(
        "AV Tools Settings", "enable_dependent_auto_permission"
    )
    if current_value is None:
        frappe.db.set_single_value(
            "AV Tools Settings",
            "enable_dependent_auto_permission",
            cint(legacy_value) if legacy_value is not None else 1,
        )
    elif legacy_value is not None:
        frappe.db.set_single_value(
            "AV Tools Settings",
            "enable_dependent_auto_permission",
            cint(legacy_value),
        )

    frappe.db.delete(
        "Singles",
        {
            "doctype": "CSF TZ Settings",
            "field": "enable_dependent_auto_permission",
        },
    )


def _delete_legacy_custom_fields():
    for name in (
        "CSF TZ Settings-enable_dependent_auto_permission",
    ):
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name)
