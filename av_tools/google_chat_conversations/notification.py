from __future__ import annotations

import hashlib
import re
import uuid
from html import unescape

import frappe
from frappe.utils import get_url_to_form, now_datetime

from av_tools.google_chat_conversations.api import GoogleChatAPIError, GoogleChatClient

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")


def enqueue_notification_log(doc, method=None):
	if not getattr(doc, "for_user", None):
		return

	try:
		settings = frappe.get_single("Google Chat Settings")
	except Exception:
		return

	if not settings.enabled:
		return

	frappe.enqueue(
		"av_tools.google_chat_conversations.notification.process_notification_log",
		queue="short",
		enqueue_after_commit=True,
		notification_log_name=doc.name,
	)


def process_notification_log(notification_log_name):
	settings = frappe.get_single("Google Chat Settings")
	if not settings.enabled:
		return

	notification = frappe.get_doc("Notification Log", notification_log_name)
	if not notification.for_user:
		return

	delivery = _get_or_create_delivery(notification)
	if delivery.status == "Sent":
		return

	try:
		chat_user = _get_or_create_chat_user(notification.for_user)
		if not chat_user.enabled:
			_mark_skipped(delivery, "Google Chat notifications are disabled for this user")
			return

		client = GoogleChatClient(settings=settings)
		mode = settings.delivery_mode or "Personal Threaded Space"
		thread_key = None
		conversation = None

		if mode == "Direct Message":
			space_name = client.find_direct_message(chat_user)
		else:
			space_name = client.ensure_personal_threaded_space(chat_user)
			if notification.document_type and notification.document_name:
				conversation, thread_key = _get_or_create_conversation(notification, space_name)

		text = format_notification_message(notification, settings)
		request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{frappe.local.site}:notification-log:{notification.name}"))
		response = client.send_message(
			space_name=space_name,
			text=text,
			request_id=request_id,
			thread_key=thread_key,
		)

		thread_name = (response.get("thread") or {}).get("name")
		message_name = response.get("name")
		if conversation:
			conversation.db_set("thread_name", thread_name or conversation.thread_name, update_modified=False)
			conversation.db_set("last_notification_log", notification.name, update_modified=False)
			conversation.db_set("last_message_name", message_name, update_modified=False)
			conversation.db_set("last_activity", now_datetime(), update_modified=False)

		delivery.db_set("status", "Sent", update_modified=False)
		delivery.db_set("mode", mode, update_modified=False)
		delivery.db_set("space_name", space_name, update_modified=False)
		delivery.db_set("conversation", conversation.name if conversation else None, update_modified=False)
		delivery.db_set("thread_name", thread_name, update_modified=False)
		delivery.db_set("google_message_name", message_name, update_modified=False)
		delivery.db_set("sent_on", now_datetime(), update_modified=False)
		delivery.db_set("error", None, update_modified=False)
	except Exception as exc:
		delivery.db_set("status", "Failed", update_modified=False)
		delivery.db_set("attempts", (delivery.attempts or 0) + 1, update_modified=False)
		delivery.db_set("error", str(exc)[:10000], update_modified=False)
		if not isinstance(exc, GoogleChatAPIError):
			frappe.log_error(frappe.get_traceback(), "Google Chat Notification Failure")
		raise


def format_notification_message(notification, settings=None):
	subject = _plain_text(notification.subject or "ERPNext notification")
	parts = [subject]

	if notification.document_type and notification.document_name:
		parts.append(f"{notification.document_type}: {notification.document_name}")
		if settings is None or settings.include_document_link:
			try:
				parts.append(get_url_to_form(notification.document_type, notification.document_name))
			except Exception:
				pass

	if notification.type:
		parts.append(f"Notification: {notification.type}")

	return "\n\n".join(part for part in parts if part)


def make_thread_key(document_type, document_name):
	raw = f"{frappe.local.site}|{document_type}|{document_name}"
	return f"erpnext-{hashlib.sha256(raw.encode()).hexdigest()}"


def make_conversation_key(user, document_type, document_name):
	raw = f"{frappe.local.site}|{user}|{document_type}|{document_name}"
	return hashlib.sha256(raw.encode()).hexdigest()


def _plain_text(value):
	value = unescape(_TAG_RE.sub("", value or ""))
	value = _WHITESPACE_RE.sub(" ", value)
	return value.strip()


def _get_or_create_chat_user(user):
	if frappe.db.exists("Google Chat User", user):
		return frappe.get_doc("Google Chat User", user)

	email = frappe.db.get_value("User", user, "email") or user
	doc = frappe.get_doc(
		{
			"doctype": "Google Chat User",
			"user": user,
			"google_email": email,
			"enabled": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _get_or_create_conversation(notification, space_name):
	key = make_conversation_key(
		notification.for_user,
		notification.document_type,
		notification.document_name,
	)
	thread_key = make_thread_key(notification.document_type, notification.document_name)

	if frappe.db.exists("Google Chat Conversation", key):
		return frappe.get_doc("Google Chat Conversation", key), thread_key

	doc = frappe.get_doc(
		{
			"doctype": "Google Chat Conversation",
			"conversation_key": key,
			"user": notification.for_user,
			"document_type": notification.document_type,
			"document_name": notification.document_name,
			"space_name": space_name,
			"thread_key": thread_key,
			"first_notification_log": notification.name,
			"last_notification_log": notification.name,
			"last_activity": now_datetime(),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc, thread_key


def _get_or_create_delivery(notification):
	name = frappe.db.get_value("Google Chat Delivery Log", {"notification_log": notification.name}, "name")
	if name:
		return frappe.get_doc("Google Chat Delivery Log", name)

	doc = frappe.get_doc(
		{
			"doctype": "Google Chat Delivery Log",
			"notification_log": notification.name,
			"user": notification.for_user,
			"status": "Queued",
			"attempts": 0,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _mark_skipped(delivery, reason):
	delivery.db_set("status", "Skipped", update_modified=False)
	delivery.db_set("error", reason, update_modified=False)
