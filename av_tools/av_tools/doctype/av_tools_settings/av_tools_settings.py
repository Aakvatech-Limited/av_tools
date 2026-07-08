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


class AVToolsSettings(Document):
	def on_update(self):
		self.manage_parallel_approval_functionality()

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
