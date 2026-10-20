# Copyright (c) 2022, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SQLProcess(Document):
	def validate(self):
		self.process = []

	@frappe.whitelist()
	def get_process(self):
		frappe.throw(
			_("Database process management is unavailable in AV Tools."),
			frappe.PermissionError,
		)

	@frappe.whitelist()
	def kill_process(self, pid):
		frappe.throw(
			_("Database process management is unavailable in AV Tools."),
			frappe.PermissionError,
		)
