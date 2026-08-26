import frappe


CUSTOM_FIELDS = ("Account-item",)


def execute():
	for cf_name in CUSTOM_FIELDS:
		if frappe.db.exists("Custom Field", cf_name):
			frappe.db.set_value("Custom Field", cf_name, "module", "Av Tools")
