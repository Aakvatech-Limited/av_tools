import frappe
from frappe import _

SHARED_MODULES = ("AuthOTP", "Feedback", "AI Integration", "Trade In")


def before_install():
	"""Let Frappe register legacy modules without deleting another app's modules."""
	modules = frappe.get_module_list("av_tools")
	# Validate every collision before making changes. Frappe's installer inserts
	# Module Defs afterwards; only their metadata rows need to be re-registered.
	for module in modules:
		if not frappe.db.exists("Module Def", module):
			continue
		owner = frappe.db.get_value("Module Def", module, "app_name")
		if owner == "av_tools" or (module in SHARED_MODULES and owner == "csf_tz"):
			continue
		frappe.throw(_("Module {0} already belongs to {1}; installation stopped.").format(module, owner))

	for module in modules:
		if frappe.db.exists("Module Def", module):
			frappe.db.delete("Module Def", {"name": module})
	# The installer controls the transaction. Do not commit a partial handover.


def reconcile_shared_modules():
	"""Transfer legacy ownership without deleting DocTypes, tables or OTP data."""
	for module in SHARED_MODULES:
		if not frappe.db.exists("Module Def", module):
			continue
		owner = frappe.db.get_value("Module Def", module, "app_name")
		if owner == "csf_tz":
			frappe.db.set_value("Module Def", module, "app_name", "av_tools", update_modified=False)

	# Older CSF TZ releases also shipped a second OTP Register in their core module.
	if frappe.db.get_value("DocType", "OTP Register", "module") == "CSF TZ":
		frappe.db.set_value("DocType", "OTP Register", "module", "AuthOTP", update_modified=False)
		frappe.clear_cache(doctype="OTP Register")
