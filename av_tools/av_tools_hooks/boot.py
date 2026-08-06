import frappe

from av_tools.av_tools_hooks.capture import (
	DEFAULT_CAPTURE_SETTINGS,
	get_capture_boot_settings,
)
from av_tools.av_tools_hooks.parallel_approval import _get_approval_doctypes


def boot_session(bootinfo):
	try:
		bootinfo.parallel_approval_doctypes = list(_get_approval_doctypes())
	except Exception:
		frappe.log_error(frappe.get_traceback(), "AV Tools: boot_session approval data failed")
		bootinfo.parallel_approval_doctypes = []

	try:
		bootinfo.av_tools_capture_settings = get_capture_boot_settings()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "AV Tools: boot_session capture settings failed")
		bootinfo.av_tools_capture_settings = DEFAULT_CAPTURE_SETTINGS.copy()
