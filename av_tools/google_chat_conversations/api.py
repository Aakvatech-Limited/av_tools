from __future__ import annotations

import json
import uuid

import frappe
import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

API_BASE = "https://chat.googleapis.com/v1"
SCOPES = [
	"https://www.googleapis.com/auth/chat.bot",
	"https://www.googleapis.com/auth/chat.app.spaces.create",
	"https://www.googleapis.com/auth/chat.app.memberships",
]


class GoogleChatAPIError(Exception):
	pass


class GoogleChatClient:
	def __init__(self, settings=None):
		self.settings = settings or frappe.get_single("Google Chat Settings")
		self.timeout = int(self.settings.request_timeout or 15)
		self._credentials = None

	def _get_credentials(self):
		if self._credentials and self._credentials.valid:
			return self._credentials

		credential_json = self.settings.get_password("service_account_json", raise_exception=False)
		if not credential_json:
			raise GoogleChatAPIError("Google Chat service account JSON is not configured")

		try:
			info = json.loads(credential_json)
		except json.JSONDecodeError as exc:
			raise GoogleChatAPIError("Google Chat service account JSON is invalid") from exc

		credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
		credentials.refresh(GoogleAuthRequest())
		self._credentials = credentials
		return credentials

	def _request(self, method, path, params=None, json_body=None, allow_statuses=None):
		allow_statuses = set(allow_statuses or [])
		credentials = self._get_credentials()
		headers = {
			"Authorization": f"Bearer {credentials.token}",
			"Content-Type": "application/json; charset=utf-8",
		}
		url = f"{API_BASE}/{path.lstrip('/')}"

		try:
			response = requests.request(
				method,
				url,
				params=params,
				json=json_body,
				headers=headers,
				timeout=self.timeout,
			)
		except requests.RequestException as exc:
			raise GoogleChatAPIError(f"Google Chat API request failed: {exc}") from exc

		if response.status_code >= 400 and response.status_code not in allow_statuses:
			detail = response.text[:2000]
			raise GoogleChatAPIError(f"Google Chat API returned HTTP {response.status_code}: {detail}")

		if not response.content:
			return {}

		try:
			return response.json()
		except ValueError:
			return {}

	def ensure_personal_threaded_space(self, chat_user):
		if chat_user.personal_space_name:
			return chat_user.personal_space_name

		email = chat_user.google_email or chat_user.user
		prefix = self.settings.personal_space_prefix or "ERPNext Notifications"
		display_name = chat_user.personal_space_display_name or f"{prefix} - {email}"
		request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{frappe.local.site}:google-chat-space:{email}"))
		body = {
			"spaceType": "SPACE",
			"displayName": display_name[:128],
			"customer": self.settings.workspace_customer or "customers/my_customer",
			"spaceDetails": {
				"description": "Private ERPNext notification space managed by the ERPNext Google Chat integration."
			},
		}
		space = self._request("POST", "spaces", params={"requestId": request_id}, json_body=body)
		space_name = space.get("name")
		if not space_name:
			raise GoogleChatAPIError("Google Chat did not return a space resource name")

		membership_body = {
			"member": {
				"name": f"users/{email}",
				"type": "HUMAN",
			}
		}
		self._request(
			"POST",
			f"{space_name}/members",
			json_body=membership_body,
			allow_statuses={409},
		)

		chat_user.db_set("personal_space_name", space_name, update_modified=False)
		chat_user.db_set("personal_space_display_name", display_name[:128], update_modified=False)
		return space_name

	def find_direct_message(self, chat_user):
		if chat_user.direct_message_space_name:
			return chat_user.direct_message_space_name

		if not chat_user.google_chat_user_id:
			raise GoogleChatAPIError(
				"Direct Message mode requires Google Chat User ID because app-authenticated "
				"findDirectMessage does not support an email alias"
			)

		space = self._request(
			"GET",
			"spaces:findDirectMessage",
			params={"name": f"users/{chat_user.google_chat_user_id}"},
		)
		space_name = space.get("name")
		if not space_name:
			raise GoogleChatAPIError("Google Chat did not return a direct-message space")

		chat_user.db_set("direct_message_space_name", space_name, update_modified=False)
		return space_name

	def send_message(self, space_name, text, request_id, thread_key=None):
		params = {"requestId": request_id}
		body = {"text": text}

		if thread_key:
			body["thread"] = {"threadKey": thread_key}
			params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"

		return self._request(
			"POST",
			f"{space_name}/messages",
			params=params,
			json_body=body,
		)
