import frappe


MODULES_TO_CLAIM = ("AuthOTP", "Feedback", "AI Integration")


def before_install():
	for module in MODULES_TO_CLAIM:
		if frappe.db.exists("Module Def", module):
			frappe.db.delete("Module Def", {"name": module})
