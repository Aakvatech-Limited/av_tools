# Copyright (c) 2022, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class SQLProcess(Document):
	def validate(self):
		self.process = []

	@frappe.whitelist()
	def get_process(self):
		process = frappe.db.sql(
			"""
                select id, time, info
                from information_schema.processlist
                WHERE info IS NOT NULL
            """,
			as_dict=True,
		)
		return process

	@frappe.whitelist()
	def kill_process(self, pid: int):
		frappe.msgprint(_("Killing process {0}").format(pid), alert=True, indicator="orange")
		try:
			frappe.db.sql("KILL %s", (cint(pid),))
		except Exception:
			frappe.msgprint(_("Process not found"), alert=True, indicator="red")
			return False
		frappe.msgprint(_("Process killed"), alert=True, indicator="green")
		return True
