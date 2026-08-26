import frappe

MODULE_NAME = "Feedback"
APP_NAME = "av_tools"


def execute():
	if frappe.db.exists("Module Def", MODULE_NAME):
		frappe.db.set_value("Module Def", MODULE_NAME, "app_name", APP_NAME, update_modified=False)
