# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class InspectionRecord(Document):
	def validate(self):
		self.validate_dates()
		self.set_title()

	def set_title(self):
		if not self.inspection_title:
			self.inspection_title = f"{self.inspection_type} - {self.inspection_date}"

	def validate_dates(self):
		if self.next_inspection_due and self.inspection_date:
			if getdate(self.next_inspection_due) <= getdate(self.inspection_date):
				frappe.throw(
					_("Next Inspection Due date must be after the Inspection Date"),
					title=_("Invalid Dates"),
				)

		if self.corrective_action_deadline and self.inspection_date:
			if getdate(self.corrective_action_deadline) < getdate(self.inspection_date):
				frappe.throw(
					_("Corrective Action Deadline cannot be before the Inspection Date"),
					title=_("Invalid Dates"),
				)
