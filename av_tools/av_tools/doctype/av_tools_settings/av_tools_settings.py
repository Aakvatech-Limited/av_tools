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
from av_tools.trade_in.utils import (
	add_trade_in_control_account,
	add_trade_in_item,
	add_trade_in_module,
	delete_trade_in_item_and_account,
	set_negative_rates_for_items,
)


class AVToolsSettings(Document):
	def on_update(self):
		self.manage_trade_in_functionality()
		self.manage_parallel_approval_functionality()

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

		new_doctypes = {
			row.doctype_name
			for row in (self.approval_doctype or [])
			if row.doctype_name
		}

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
				frappe.msgprint(_("Could not create approver fields on {0}: {1}").format(dt, e))

		for dt in existing_doctypes - new_doctypes:
			try:
				delete_approval_fields(dt)
				delete_approver_qr_print_format(dt)
			except Exception as e:
				frappe.log_error(f"Parallel Approval: delete fields on '{dt}': {e}", "Parallel Approval")
				frappe.msgprint(_("Could not remove approver fields from {0}: {1}").format(dt, e))
