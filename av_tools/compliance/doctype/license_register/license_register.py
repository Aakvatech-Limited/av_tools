# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate, date_diff


class LicenseRegister(Document):
	def before_save(self):
		self.validate_dates()
		self.update_status()

	def validate_dates(self):
		if self.issue_date and self.expiry_date:
			if getdate(self.issue_date) > getdate(self.expiry_date):
				frappe.throw(
					_("Issue Date cannot be after Expiry Date"),
					title=_("Invalid Dates"),
				)

	def update_status(self):
		"""Auto-update status based on expiry date."""
		if self.status in ("Suspended", "Cancelled"):
			return

		today = getdate(nowdate())
		expiry = getdate(self.expiry_date) if self.expiry_date else None

		if not expiry:
			return

		if expiry < today:
			self.status = "Expired"
		elif self.reminder_days_before and date_diff(expiry, today) <= self.reminder_days_before:
			self.status = "Pending Renewal"
		else:
			self.status = "Active"


def update_license_statuses():
	"""Scheduled job to auto-update license statuses daily.
	Called via hooks.py scheduler_events.
	"""
	licenses = frappe.get_all(
		"License Register",
		filters={"status": ("in", ["Active", "Pending Renewal"])},
		fields=["name", "expiry_date", "reminder_days_before", "status"],
	)

	today = getdate(nowdate())

	for lic in licenses:
		expiry = getdate(lic.expiry_date)
		new_status = lic.status

		if expiry < today:
			new_status = "Expired"
		elif lic.reminder_days_before and date_diff(expiry, today) <= lic.reminder_days_before:
			new_status = "Pending Renewal"

		if new_status != lic.status:
			frappe.db.set_value("License Register", lic.name, "status", new_status)

