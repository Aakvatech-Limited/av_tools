import frappe

from av_tools.utils.legacy_settings import adopt_legacy_value


def execute():
	adopt_legacy_value("enable_dependent_auto_permission", default=1, as_int=True)
	_delete_legacy_custom_fields()


def _delete_legacy_custom_fields():
	for name in ("CSF TZ Settings-enable_dependent_auto_permission",):
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name)
