# Copyright (c) 2021, Aakvatech and contributors
# For license information, please see license.txt

import ast

import frappe
from frappe import _
from frappe.model.document import Document


class SQLCommand(Document):
	def on_submit(self):
		# This legacy DocType must never be a general-purpose SQL executor.
		if (self.sql_text or "").strip():
			frappe.throw(_("Executing SQL text through SQL Command is disabled."))

		if not self.doctype_name or not (self.names or "").strip():
			frappe.throw(_("Select a DocType and document names."))

		if frappe.session.user != "Administrator":
			frappe.throw(
				_("Only Administrator may delete documents through SQL Command."), frappe.PermissionError
			)

		if not frappe.db.get_single_value("AV Tools Settings", "allow_delete_in_sql_command"):
			frappe.throw(_("Deletion through SQL Command is disabled in AV Tools Settings."))

		meta = frappe.get_meta(self.doctype_name)
		if meta.issingle or meta.istable or meta.is_virtual:
			frappe.throw(_("Only regular, stored documents can be deleted through SQL Command."))

		try:
			# Support the old comma-separated quoted-name format without treating
			# user-provided values as SQL identifiers or expressions.
			names = ast.literal_eval("[" + self.names.strip() + "]")
		except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
			frappe.throw(_("Names must be a comma-separated list of quoted document names."))

		if not isinstance(names, list) or not 1 <= len(names) <= 100:
			frappe.throw(_("Specify between 1 and 100 document names."))
		if any(not isinstance(name, str) or not name.strip() for name in names):
			frappe.throw(_("Every document name must be a non-empty quoted string."))
		if len(set(names)) != len(names):
			frappe.throw(_("Duplicate document names are not allowed."))

		for name in names:
			# Preserve Frappe document lifecycle, link checks and deletion hooks.
			frappe.delete_doc(self.doctype_name, name, ignore_permissions=False)
