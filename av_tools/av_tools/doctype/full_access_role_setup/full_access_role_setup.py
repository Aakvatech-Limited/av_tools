import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from av_tools.permissions.full_access import sync_full_access

FULL_ACCESS_AUTHORIZED_USER = "Administrator"
FULL_ACCESS_CONSENT_TTL = 600
FULL_ACCESS_CONSENT_CACHE_KEY = "av_tools:full_access_consent"


class FullAccessRoleSetup(Document):
	def validate(self):
		if self.is_new() and self.enable_full_access_role:
			frappe.throw(
				_("Save the company setup first, then enable FULL ACCESS and accept the authorization warning.")
			)

		if not self.has_value_changed("enable_full_access_role"):
			return

		if frappe.session.user != FULL_ACCESS_AUTHORIZED_USER:
			frappe.throw(_("Only Administrator is authorized to change FULL ACCESS configuration."))

		if self.enable_full_access_role:
			consent = _get_consent(self.name)
			if not consent:
				frappe.throw(
					_("You must review the FULL ACCESS warning and click I Accept before enabling this setup.")
				)

			self.consent_accepted_by = frappe.session.user
			self.consent_accepted_on = now_datetime()

	def on_update(self):
		if not self.has_value_changed("enable_full_access_role"):
			return

		_clear_consent(self.name)

		if self.enable_full_access_role:
			sync_full_access()


def _consent_cache_key(setup_name):
	return f"{FULL_ACCESS_CONSENT_CACHE_KEY}:{frappe.session.user}:{setup_name}"


def _get_consent(setup_name):
	return frappe.cache.get_value(_consent_cache_key(setup_name), expires=True)


def _clear_consent(setup_name):
	frappe.cache.delete_value(_consent_cache_key(setup_name))


@frappe.whitelist()
def accept_full_access_consent(setup_name):
	if frappe.session.user != FULL_ACCESS_AUTHORIZED_USER:
		frappe.throw(_("Only Administrator is authorized to accept FULL ACCESS consent."))

	if not setup_name or not frappe.db.exists("Full Access Role Setup", setup_name):
		frappe.throw(_("Save the Full Access Role Setup before accepting consent."))

	setup = frappe.get_doc("Full Access Role Setup", setup_name)

	consent_text = (
		f"I understand that enabling FULL ACCESS for setup {setup.name} ({setup.company}) activates a "
		"site-wide role policy granting broad access to eligible non-Frappe DocTypes, Reports, Pages "
		"and Workspaces. I confirm that I am the authorized Lead Implementor using Administrator. I Accept."
	)

	frappe.get_doc(
		{
			"doctype": "Activity Log",
			"subject": f"FULL ACCESS consent accepted - {setup.company}",
			"content": consent_text,
			"status": "Success",
			"reference_doctype": "Full Access Role Setup",
			"reference_name": setup.name,
			"user": frappe.session.user,
			"ip_address": getattr(frappe.local, "request_ip", None),
		}
	).insert(ignore_permissions=True)

	frappe.cache.set_value(
		_consent_cache_key(setup.name),
		{"accepted": True},
		expires_in_sec=FULL_ACCESS_CONSENT_TTL,
	)

	return {"accepted": True, "expires_in_seconds": FULL_ACCESS_CONSENT_TTL}
