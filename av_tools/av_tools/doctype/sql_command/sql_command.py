# Copyright (c) 2021, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SQLCommand(Document):
	def on_submit(self):
		if self.sql_text and "DELETE" in self.sql_text.upper():
			return

		delete_allowed = frappe.db.get_single_value("AV Tools Settings", "allow_delete_in_sql_command")
		if self.doctype_name:
			if delete_allowed and not self.sql_text and self.names:
				frappe.db.sql(f"DELETE FROM `tab{self.doctype_name}` WHERE NAME IN ({self.names})")
		elif self.sql_text:
			frappe.db.sql(self.sql_text)

		frappe.db.commit()
