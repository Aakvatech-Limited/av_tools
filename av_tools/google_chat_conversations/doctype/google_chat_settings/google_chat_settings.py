import json

import frappe
from frappe.model.document import Document


class GoogleChatSettings(Document):
	def validate(self):
		if not self.enabled:
			return

		credential_json = self.get_password("service_account_json", raise_exception=False)
		if not credential_json:
			frappe.throw("Service Account JSON is required when Google Chat Conversations is enabled")

		try:
			info = json.loads(credential_json)
		except json.JSONDecodeError:
			frappe.throw("Service Account JSON must contain valid JSON")

		for key in ("client_email", "private_key", "token_uri"):
			if not info.get(key):
				frappe.throw(f"Service Account JSON is missing required key: {key}")
