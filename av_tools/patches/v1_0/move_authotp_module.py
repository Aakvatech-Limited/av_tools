import frappe


def execute():
	if frappe.db.exists("Module Def", "AuthOTP"):
		frappe.db.set_value("Module Def", "AuthOTP", "app_name", "av_tools")
