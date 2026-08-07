import frappe
from frappe.utils import cint

SETTINGS_DOCTYPE = "AV Tools Settings"
DEFAULT_CAPTURE_SETTINGS = {
	"enabled": False,
	"ideal_width": 1920,
	"ideal_height": 1080,
	"min_width": 0,
	"min_height": 0,
}


def _sanitize_positive_int(value, default=0):
	value = cint(value)
	if value > 0:
		return value
	return default


def _get_capture_settings():
	settings = DEFAULT_CAPTURE_SETTINGS.copy()

	try:
		values = frappe.db.get_singles_dict(SETTINGS_DOCTYPE) or {}
	except Exception:
		return settings

	settings["enabled"] = bool(cint(values.get("enable_camera_capture_override")))
	settings["ideal_width"] = _sanitize_positive_int(
		values.get("camera_capture_ideal_width"), DEFAULT_CAPTURE_SETTINGS["ideal_width"]
	)
	settings["ideal_height"] = _sanitize_positive_int(
		values.get("camera_capture_ideal_height"), DEFAULT_CAPTURE_SETTINGS["ideal_height"]
	)
	settings["min_width"] = _sanitize_positive_int(
		values.get("camera_capture_min_width"), DEFAULT_CAPTURE_SETTINGS["min_width"]
	)
	settings["min_height"] = _sanitize_positive_int(
		values.get("camera_capture_min_height"), DEFAULT_CAPTURE_SETTINGS["min_height"]
	)

	return settings


@frappe.whitelist()
def get_capture_settings():
	return _get_capture_settings()
