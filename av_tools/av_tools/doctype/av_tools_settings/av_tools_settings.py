# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from av_tools.av_tools_hooks.parallel_approval import (
	clear_approval_cache,
	create_approval_fields,
	create_approver_qr_print_format,
	delete_approval_fields,
	delete_approver_qr_print_format,
)
from av_tools.permissions.full_access import sync_full_access
from av_tools.trade_in.utils import (
	add_trade_in_control_account,
	add_trade_in_item,
	add_trade_in_module,
	delete_trade_in_item_and_account,
	set_negative_rates_for_items,
)

FULL_ACCESS_CONSENT_CACHE_KEY = "av_tools:full_access_consent"
FULL_ACCESS_CONSENT_TTL = 600
FULL_ACCESS_AUTHORIZED_USER = "Administrator"


class AVToolsSettings(Document):
	def validate(self):
		self.validate_full_access_setting_change()

	def validate_full_access_setting_change(self):
		if not self.has_value_changed("enable_full_access_role"):
			return

		if frappe.session.user != FULL_ACCESS_AUTHORIZED_USER:
			frappe.throw(_("Only Administrator is authorized to change Enable FULL ACCESS Role."))

		field = frappe.get_meta(self.doctype).get_field("enable_full_access_role")
		if field and (field.hidden or field.read_only):
			frappe.throw(
				_(
					"Enable FULL ACCESS Role is deliberately locked. "
					"Use Property Setters to make the field visible and editable before changing it."
				)
			)

		if self.enable_full_access_role and not _has_valid_full_access_consent():
			frappe.throw(
				_(
					"You must review the FULL ACCESS warning and click I Accept "
					"before enabling this setting."
				)
			)

	def on_update(self):
		self.manage_parallel_approval_functionality()
		self.manage_trade_in_functionality()
		self.manage_full_access_role()

	def manage_full_access_role(self):
		if not self.has_value_changed("enable_full_access_role") or not self.enable_full_access_role:
			return

		_clear_full_access_consent()

		try:
			sync_full_access()
			frappe.msgprint(_("FULL ACCESS role policy has been enabled and synchronized."))
		except Exception:
			frappe.log_error(frappe.get_traceback(), "FULL ACCESS synchronization failed")
			frappe.msgprint(_("FULL ACCESS role was enabled, but synchronization encountered an error. Check Error Log."))

	def manage_trade_in_functionality(self):
		if not self.has_value_changed("enable_trade_in"):
			return

		# Check if the feature is being enabled
		if self.enable_trade_in:
			try:
				add_trade_in_module()  # Add Trade In module
				add_trade_in_item()  # Create Trade In item
				add_trade_in_control_account()  # Create Control Account
				set_negative_rates_for_items()  # Allow negative rates for items
				frappe.msgprint(_("Trade In feature has been successfully enabled."))
			except Exception as e:
				# Log the error and notify the user
				frappe.log_error(f"Error enabling Trade In feature: {e!s}")
				frappe.msgprint(_("Failed to enable Trade In feature: {0}").format(str(e)))
		else:
			# If the feature is being disabled, delete the associated item and account
			try:
				delete_trade_in_item_and_account()  # Delete Trade In item and Control Account
				frappe.msgprint(_("Trade In feature has been successfully disabled."))
			except Exception as e:
				# Log the error and notify the user
				frappe.log_error(f"Error disabling Trade In feature: {e!s}")
				frappe.msgprint(_("Failed to disable Trade In feature: {0}").format(str(e)))

	def manage_parallel_approval_functionality(self):
		clear_approval_cache()

		new_doctypes = {row.doctype_name for row in (self.approval_doctype or []) if row.doctype_name}

		existing_doctypes = set(
			frappe.get_all(
				"Custom Field",
				filters={"fieldname": "custom_av_approvers_tab"},
				pluck="dt",
			)
		)

		# Always create/update for every doctype in the list so field
		# position and definition stay in sync with any code changes.
		for dt in new_doctypes:
			try:
				create_approval_fields(dt)
				create_approver_qr_print_format(dt)
			except Exception as e:
				frappe.log_error(f"Parallel Approval: create fields on '{dt}': {e}", "Parallel Approval")
				frappe.msgprint(_("Could not create approver fields on {0}: {1}").format(dt, str(e)))

		for dt in existing_doctypes - new_doctypes:
			try:
				delete_approval_fields(dt)
				delete_approver_qr_print_format(dt)
			except Exception as e:
				frappe.log_error(f"Parallel Approval: delete fields on '{dt}': {e}", "Parallel Approval")
				frappe.msgprint(_("Could not remove approver fields from {0}: {1}").format(dt, str(e)))



def _consent_cache_key():
	return f"{FULL_ACCESS_CONSENT_CACHE_KEY}:{frappe.session.user}"


def _has_valid_full_access_consent():
	return bool(frappe.cache.get_value(_consent_cache_key(), expires=True))


def _clear_full_access_consent():
	frappe.cache.delete_value(_consent_cache_key())


def _full_access_field_is_unlocked():
	field = frappe.get_meta("AV Tools Settings").get_field("enable_full_access_role")
	return bool(field and not field.hidden and not field.read_only)


@frappe.whitelist()
def accept_full_access_consent():
	if frappe.session.user != FULL_ACCESS_AUTHORIZED_USER:
		frappe.throw(_("Only Administrator is authorized to accept FULL ACCESS consent."))

	if not _full_access_field_is_unlocked():
		frappe.throw(
			_(
				"Enable FULL ACCESS Role is still hidden or read-only. "
				"Unlock it deliberately with Property Setters before accepting consent."
			)
		)

	consent_text = (
		"I understand that enabling FULL ACCESS grants the FULL ACCESS role broad permissions "
		"to all eligible non-Frappe DocTypes, Reports, Pages and Workspaces, and that this "
		"privileged action must only be performed by the authorized Lead Implementor using "
		"the Administrator account. I Accept."
	)

	frappe.get_doc(
		{
			"doctype": "Activity Log",
			"subject": "FULL ACCESS consent accepted",
			"content": consent_text,
			"status": "Success",
			"reference_doctype": "AV Tools Settings",
			"reference_name": "AV Tools Settings",
			"user": frappe.session.user,
			"ip_address": getattr(frappe.local, "request_ip", None),
		}
	).insert(ignore_permissions=True)

	frappe.cache.set_value(
		_consent_cache_key(),
		1,
		expires_in_sec=FULL_ACCESS_CONSENT_TTL,
	)

	return {"accepted": True, "expires_in_seconds": FULL_ACCESS_CONSENT_TTL}
