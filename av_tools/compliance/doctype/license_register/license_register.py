# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.model.document import Document
from frappe.utils import date_diff, formatdate, getdate, nowdate
from frappe.utils.user import get_users_with_role


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
		fields=[
			"name",
			"license_name",
			"license_number",
			"license_type",
			"expiry_date",
			"reminder_days_before",
			"status",
			"notify_role",
		],
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
			if lic.notify_role:
				users = get_users_with_role(lic.notify_role)
				if users:
					_send_license_notification(lic, new_status, today, users)


def _send_license_notification(lic, new_status, today, users):
	"""Send notification to users when a license transitions to
	Pending Renewal or Expired using frappe's built-in notification system.
	"""

	days_remaining = date_diff(getdate(lic.expiry_date), today)

	if new_status == "Expired":
		subject = _(f"License Expired: {lic.license_name}")
		message = _(
			f"The license <b>{lic.license_name}</b> ({lic.license_number}) of type <b>{lic.license_type}</b> has <b>expired</b> on {formatdate(lic.expiry_date)}."
			"<br><br>Please take immediate action to renew it."
		)
	else:
		subject = _(f"License Expiring Soon: {lic.license_name}")
		message = _(
			f"The license <b>{lic.license_name}</b> ({lic.license_number}) of type <b>{lic.license_type}</b> will expire on {formatdate(lic.expiry_date)}"
			" (<b>{days_remaining} days remaining</b>)."
			"<br><br>Please initiate the renewal process."
		)

	enqueue_create_notification(
		users,
		{
			"type": "Alert",
			"document_type": "License Register",
			"document_name": lic.name,
			"subject": subject,
			"email_content": message,
			"from_user": frappe.session.user,
		},
	)
