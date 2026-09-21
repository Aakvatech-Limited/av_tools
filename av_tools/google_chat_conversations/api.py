from __future__ import annotations

import base64
import json
import time
import uuid

import frappe
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API_BASE = "https://chat.googleapis.com/v1"
SCOPES = " ".join(
	[
		"https://www.googleapis.com/auth/chat.bot",
		"https://www.googleapis.com/auth/chat.app.spaces.create",
		"https://www.googleapis.com/auth/chat.app.memberships",
	]
)


class GoogleChatAPIError(Exception):
	pass


def _b64url(value):
	return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class GoogleChatClient:
	def __init__(self, settings=None):
		self.settings = settings or frappe.get_single("Google Chat Settings")
		self.timeout = int(self.settings.request_timeout or 15)
		self._access_token = None
		self._access_token_expires = 0

	def _get_service_account_info(self):
		credential_json = self.settings.get_password("service_account_json", raise_exception=False)
		if not credential_json:
			raise GoogleChatAPIError("Google Chat service account JSON is not configured")
		try:
			return json.loads(credential_json)
		except json.JSONDecodeError as exc:
			raise GoogleChatAPIError("Google Chat service account JSON is invalid") from exc

	def _get_access_token(self):
		now = int(time.time())
		if self._access_token and now < self._access_token_expires - 60:
			return self._access_token

		info = self._get_service_account_info()
		token_uri = info.get("token_uri") or "https://oauth2.googleapis.com/token"
		header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
		claims = {
			"iss": info.get("client_email"),
			"scope": SCOPES,
			"aud": token_uri,
			"iat": now,
			"exp": now + 3600,
		}
		payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
		unsigned = f"{header}.{payload}".encode()
		try:
			private_key = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
		except (KeyError, TypeError, ValueError) as exc:
			raise GoogleChatAPIError("Google Chat service account private key is invalid") from exc
		signature = private_key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
		assertion = f"{header}.{payload}.{_b64url(signature)}"

		try:
			response = requests.post(
				token_uri,
				data={
					"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
					"assertion": assertion,
				},
				timeout=self.timeout,
			)
		except requests.RequestException as exc:
			raise GoogleChatAPIError(f"Google OAuth token request failed: {exc}") from exc
		if response.status_code >= 400:
			raise GoogleChatAPIError(f"Google OAuth token request returned HTTP {response.status_code}: {response.text[:2000]}")
		data = response.json()
		self._access_token = data.get("access_token")
		if not self._access_token:
			raise GoogleChatAPIError("Google OAuth token response did not contain an access token")
		self._access_token_expires = now + int(data.get("expires_in") or 3600)
		return self._access_token

	def _request(self, method, path, params=None, json_body=None, allow_statuses=None):
		allow_statuses = set(allow_statuses or [])
		headers = {
			"Authorization": f"Bearer {self._get_access_token()}",
			"Content-Type": "application/json; charset=utf-8",
		}
		url = f"{API_BASE}/{path.lstrip('/')}"
		try:
			response = requests.request(method, url, params=params, json=json_body, headers=headers, timeout=self.timeout)
		except requests.RequestException as exc:
			raise GoogleChatAPIError(f"Google Chat API request failed: {exc}") from exc
		if response.status_code >= 400 and response.status_code not in allow_statuses:
			raise GoogleChatAPIError(f"Google Chat API returned HTTP {response.status_code}: {response.text[:2000]}")
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
			"spaceDetails": {"description": "Private ERPNext notification space managed by the ERPNext Google Chat integration."},
		}
		space = self._request("POST", "spaces", params={"requestId": request_id}, json_body=body)
		space_name = space.get("name")
		if not space_name:
			raise GoogleChatAPIError("Google Chat did not return a space resource name")
		membership_body = {"member": {"name": f"users/{email}", "type": "HUMAN"}}
		self._request("POST", f"{space_name}/members", json_body=membership_body, allow_statuses={409})
		chat_user.db_set("personal_space_name", space_name, update_modified=False)
		chat_user.db_set("personal_space_display_name", display_name[:128], update_modified=False)
		return space_name

	def find_direct_message(self, chat_user):
		if chat_user.direct_message_space_name:
			return chat_user.direct_message_space_name
		if not chat_user.google_chat_user_id:
			raise GoogleChatAPIError("Direct Message mode requires Google Chat User ID; app-authenticated findDirectMessage does not support an email alias")
		space = self._request("GET", "spaces:findDirectMessage", params={"name": f"users/{chat_user.google_chat_user_id}"})
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
		return self._request("POST", f"{space_name}/messages", params=params, json_body=body)
