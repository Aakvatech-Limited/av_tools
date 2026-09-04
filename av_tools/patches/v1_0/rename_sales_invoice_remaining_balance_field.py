import frappe


OLD = "Sales Invoice-custom_remaining_balance"
NEW = "Sales Invoice-remaining_balance"
OLD_FIELD = "custom_remaining_balance"
NEW_FIELD = "remaining_balance"


def execute():
	if not frappe.db.exists("Custom Field", OLD):
		return

	has_old_column = frappe.db.has_column("Sales Invoice", OLD_FIELD)
	has_new_column = frappe.db.has_column("Sales Invoice", NEW_FIELD)
	if frappe.db.exists("Custom Field", NEW):
		if has_old_column and has_new_column:
			frappe.db.sql(
				"""
				update `tabSales Invoice`
				set remaining_balance = custom_remaining_balance
				where ifnull(remaining_balance, 0) = 0
				"""
			)
		elif has_old_column:
			frappe.db.rename_column("Sales Invoice", OLD_FIELD, NEW_FIELD)
		frappe.delete_doc("Custom Field", OLD, force=True, ignore_permissions=True, ignore_on_trash=True)
		return

	if has_old_column and not has_new_column:
		frappe.db.rename_column("Sales Invoice", OLD_FIELD, NEW_FIELD)
	frappe.db.set_value("Custom Field", OLD, "fieldname", NEW_FIELD)
	frappe.rename_doc("Custom Field", OLD, NEW, force=True, show_alert=False)
	frappe.clear_cache(doctype="Sales Invoice")
