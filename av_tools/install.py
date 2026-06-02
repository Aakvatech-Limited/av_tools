import frappe


def before_install():
	"""
	AuthOTP was previously owned by csf_tz. It has been moved to av_tools.
	On sites where csf_tz was installed first, the AuthOTP Module Def already
	exists in the database. Delete it here so Frappe can re-register it
	cleanly under av_tools without hitting a duplicate primary key error.

	On fresh sites where AuthOTP does not exist yet, this is a no-op.
	"""
	if frappe.db.exists("Module Def", "AuthOTP"):
		frappe.db.delete("Module Def", {"name": "AuthOTP"})
		frappe.db.commit()
