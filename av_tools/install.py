import frappe

APP_NAME = "av_tools"
MIGRATION_PATCH_PREFIX = "av_tools.patches.v1_0."


def before_install():
	"""
	Some modules were previously owned by csf_tz. They have been moved to av_tools.
	On sites where csf_tz was installed first, these Module Defs (e.g. AuthOTP, Feedback)
	already exist in the database. Delete them here so Frappe can re-register them
	cleanly under av_tools without hitting a duplicate primary key error.

	On fresh sites where they do not exist yet, this is a no-op.
	"""
	try:
		modules = frappe.get_module_list("av_tools")
	except Exception:
		modules = [
			"Av Tools",
			"Weigh Bridge",
			"AuthOTP",
			"Feedback",
			"AI Integration",
			"Compliance",
			"Trade In",
		]

	for module in modules:
		if frappe.db.exists("Module Def", module):
			frappe.db.delete("Module Def", {"name": module})

	frappe.db.commit()


def run_migration_patches():
	"""Run the csf_tz -> av_tools migrations that installing the app skipped.

	frappe.installer.install_app() calls set_all_patches_as_completed() before the after_install
	hooks, so on a site that already runs csf_tz every migration patch is recorded as done without
	ever executing. Settings, report ownership and AV Report Extension rows would then never be
	carried over. Clear those log entries and run the patches for real.
	"""
	from frappe.modules.patch_handler import get_patches_from_app, run_single

	for patch in get_patches_from_app(APP_NAME):
		if not patch.startswith(MIGRATION_PATCH_PREFIX):
			continue

		frappe.db.delete("Patch Log", {"patch": patch})
		run_single(patch)

	frappe.db.commit()
