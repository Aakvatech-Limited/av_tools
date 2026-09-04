"""Read settings that csf_tz has dropped from its DocType but still holds in the database."""

import frappe
from frappe.utils import cint

SOURCE_DOCTYPE = "CSF TZ Settings"
TARGET_DOCTYPE = "AV Tools Settings"


def get_legacy_value(fieldname):
	"""Return a CSF TZ Settings value straight from Singles.

	csf_tz removed these fields from its DocType when the feature moved here, so
	`frappe.get_meta().has_field()` no longer sees them while the stored value is still there.
	Reading Singles directly is what keeps the value the client configured.
	"""
	return frappe.db.get_value(
		"Singles",
		{"doctype": SOURCE_DOCTYPE, "field": fieldname},
		"value",
		order_by=None,
	)


def adopt_legacy_value(fieldname, default=None, as_int=False):
	"""Carry one setting over to AV Tools Settings and drop the csf_tz copy."""
	legacy_value = get_legacy_value(fieldname)

	if legacy_value is None:
		if default is not None and frappe.db.get_single_value(TARGET_DOCTYPE, fieldname) is None:
			frappe.db.set_single_value(TARGET_DOCTYPE, fieldname, default)
		return

	frappe.db.set_single_value(TARGET_DOCTYPE, fieldname, cint(legacy_value) if as_int else legacy_value)
	frappe.db.delete("Singles", {"doctype": SOURCE_DOCTYPE, "field": fieldname})
