import frappe
from frappe.utils import cint

SETTINGS_DOCTYPE = "AV Tools Settings"
DEFAULT_CAPTURE_SETTINGS = {
	"enabled": False,
	"ideal_width": 1920,
	"ideal_height": 1080,
}


def _sanitize_positive_int(value, default=0):
	value = cint(value)
	if value > 0:
		return value
	return default


@frappe.whitelist()
def get_capture_settings():
	values = frappe.db.get_singles_dict(SETTINGS_DOCTYPE) or {}

	return {
		"enabled": bool(cint(values.get("enable_camera_capture_override"))),
		"ideal_width": _sanitize_positive_int(
			values.get("camera_capture_ideal_width"), DEFAULT_CAPTURE_SETTINGS["ideal_width"]
		),
		"ideal_height": _sanitize_positive_int(
			values.get("camera_capture_ideal_height"), DEFAULT_CAPTURE_SETTINGS["ideal_height"]
		),
	}
