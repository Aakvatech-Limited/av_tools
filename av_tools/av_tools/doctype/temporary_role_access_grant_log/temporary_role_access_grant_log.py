# Copyright (c) 2025, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime


class TemporaryRoleAccessGrantLog(Document):
	def validate(self):
		"""Validate the grant log entry."""
		if (
			self.revoked_on
			and self.granted_on
			and get_datetime(self.revoked_on) < get_datetime(self.granted_on)
		):
			frappe.throw(_("Revoked On cannot be earlier than Granted On"))
