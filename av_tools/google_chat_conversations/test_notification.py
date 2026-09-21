from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from av_tools.google_chat_conversations.api import GoogleChatAPIError
from av_tools.google_chat_conversations.notification import (
	enqueue_notification_log,
	format_notification_message,
	make_conversation_key,
	make_thread_key,
	process_notification_log,
)


class FakeDoc(SimpleNamespace):
	def db_set(self, fieldname, value, update_modified=False):
		setattr(self, fieldname, value)


def _notification(**overrides):
	values = {
		"name": "NOTIF-0001",
		"subject": "<strong>You</strong> gained <strong>3</strong> points",
		"for_user": "user@example.com",
		"type": "Energy Point",
		"document_type": "Payment Entry",
		"document_name": "PE-2026-05100",
	}
	values.update(overrides)
	return FakeDoc(**values)


def _settings(**overrides):
	values = {
		"enabled": 1,
		"delivery_mode": "Personal Threaded Space",
		"include_document_link": 0,
	}
	values.update(overrides)
	return FakeDoc(**values)


def _delivery(**overrides):
	values = {
		"name": "DELIVERY-0001",
		"status": "Queued",
		"attempts": 0,
		"mode": None,
		"space_name": None,
		"conversation": None,
		"thread_name": None,
		"google_message_name": None,
		"sent_on": None,
		"error": None,
	}
	values.update(overrides)
	return FakeDoc(**values)


def _conversation(**overrides):
	values = {
		"name": "CONVERSATION-0001",
		"thread_name": None,
		"last_notification_log": None,
		"last_message_name": None,
		"last_activity": None,
	}
	values.update(overrides)
	return FakeDoc(**values)


def test_format_notification_message_strips_html():
	notification = _notification()
	message = format_notification_message(notification, _settings())

	assert "<strong>" not in message
	assert "You gained 3 points" in message
	assert "Payment Entry: PE-2026-05100" in message
	assert "Notification: Energy Point" in message


@patch("av_tools.google_chat_conversations.notification.frappe.local")
def test_thread_key_is_deterministic_and_document_specific(mock_local):
	mock_local.site = "erp.example.com"

	first = make_thread_key("Payment Entry", "PE-2026-05100")
	second = make_thread_key("Payment Entry", "PE-2026-05100")
	other = make_thread_key("Payment Entry", "PE-2026-05101")

	assert first == second
	assert first != other
	assert first.startswith("erpnext-")


@patch("av_tools.google_chat_conversations.notification.frappe.local")
def test_conversation_key_is_isolated_per_user(mock_local):
	mock_local.site = "erp.example.com"

	first = make_conversation_key("user-a@example.com", "Payment Entry", "PE-2026-05100")
	second = make_conversation_key("user-b@example.com", "Payment Entry", "PE-2026-05100")

	assert first != second


@patch("av_tools.google_chat_conversations.notification.frappe.enqueue")
@patch("av_tools.google_chat_conversations.notification.frappe.get_single")
def test_enqueue_notification_log_queues_after_commit(mock_get_single, mock_enqueue):
	mock_get_single.return_value = _settings(enabled=1)
	doc = _notification()

	enqueue_notification_log(doc)

	mock_enqueue.assert_called_once_with(
		"av_tools.google_chat_conversations.notification.process_notification_log",
		queue="short",
		enqueue_after_commit=True,
		notification_log_name=doc.name,
	)


@patch("av_tools.google_chat_conversations.notification.frappe.enqueue")
@patch("av_tools.google_chat_conversations.notification.frappe.get_single")
def test_enqueue_notification_log_does_nothing_when_disabled(mock_get_single, mock_enqueue):
	mock_get_single.return_value = _settings(enabled=0)

	enqueue_notification_log(_notification())

	mock_enqueue.assert_not_called()


@patch("av_tools.google_chat_conversations.notification.frappe.enqueue")
def test_enqueue_notification_log_ignores_missing_recipient(mock_enqueue):
	enqueue_notification_log(_notification(for_user=None))
	mock_enqueue.assert_not_called()


@patch("av_tools.google_chat_conversations.notification.GoogleChatClient")
@patch("av_tools.google_chat_conversations.notification._get_or_create_conversation")
@patch("av_tools.google_chat_conversations.notification._get_or_create_chat_user")
@patch("av_tools.google_chat_conversations.notification._get_or_create_delivery")
@patch("av_tools.google_chat_conversations.notification.frappe.get_doc")
@patch("av_tools.google_chat_conversations.notification.frappe.get_single")
@patch("av_tools.google_chat_conversations.notification.frappe.local")
def test_process_threaded_notification_sends_mocked_google_chat_message(
	mock_local,
	mock_get_single,
	mock_get_doc,
	mock_get_delivery,
	mock_get_chat_user,
	mock_get_conversation,
	mock_client_class,
):
	mock_local.site = "erp.example.com"
	settings = _settings()
	notification = _notification()
	delivery = _delivery()
	chat_user = FakeDoc(enabled=1, user=notification.for_user)
	conversation = _conversation()
	thread_key = "erpnext-test-thread"

	mock_get_single.return_value = settings
	mock_get_doc.return_value = notification
	mock_get_delivery.return_value = delivery
	mock_get_chat_user.return_value = chat_user
	mock_get_conversation.return_value = (conversation, thread_key)

	client = mock_client_class.return_value
	client.ensure_personal_threaded_space.return_value = "spaces/AAA"
	client.send_message.return_value = {
		"name": "spaces/AAA/messages/MSG1",
		"thread": {"name": "spaces/AAA/threads/THREAD1"},
	}

	process_notification_log(notification.name)

	client.ensure_personal_threaded_space.assert_called_once_with(chat_user)
	client.send_message.assert_called_once()
	kwargs = client.send_message.call_args.kwargs
	assert kwargs["space_name"] == "spaces/AAA"
	assert kwargs["thread_key"] == thread_key
	assert "You gained 3 points" in kwargs["text"]
	assert delivery.status == "Sent"
	assert delivery.google_message_name == "spaces/AAA/messages/MSG1"
	assert delivery.thread_name == "spaces/AAA/threads/THREAD1"
	assert conversation.thread_name == "spaces/AAA/threads/THREAD1"
	assert conversation.last_notification_log == notification.name


@patch("av_tools.google_chat_conversations.notification.GoogleChatClient")
@patch("av_tools.google_chat_conversations.notification._get_or_create_chat_user")
@patch("av_tools.google_chat_conversations.notification._get_or_create_delivery")
@patch("av_tools.google_chat_conversations.notification.frappe.get_doc")
@patch("av_tools.google_chat_conversations.notification.frappe.get_single")
def test_process_direct_message_never_uses_thread_key(
	mock_get_single,
	mock_get_doc,
	mock_get_delivery,
	mock_get_chat_user,
	mock_client_class,
):
	settings = _settings(delivery_mode="Direct Message")
	notification = _notification()
	delivery = _delivery()
	chat_user = FakeDoc(enabled=1)

	mock_get_single.return_value = settings
	mock_get_doc.return_value = notification
	mock_get_delivery.return_value = delivery
	mock_get_chat_user.return_value = chat_user
	client = mock_client_class.return_value
	client.find_direct_message.return_value = "spaces/DM1"
	client.send_message.return_value = {"name": "spaces/DM1/messages/MSG1"}

	process_notification_log(notification.name)

	client.find_direct_message.assert_called_once_with(chat_user)
	assert client.send_message.call_args.kwargs["thread_key"] is None
	assert delivery.mode == "Direct Message"
	assert delivery.status == "Sent"


@patch("av_tools.google_chat_conversations.notification.GoogleChatClient")
@patch("av_tools.google_chat_conversations.notification._get_or_create_chat_user")
@patch("av_tools.google_chat_conversations.notification._get_or_create_delivery")
@patch("av_tools.google_chat_conversations.notification.frappe.get_doc")
@patch("av_tools.google_chat_conversations.notification.frappe.get_single")
def test_process_skips_disabled_user(
	mock_get_single,
	mock_get_doc,
	mock_get_delivery,
	mock_get_chat_user,
	mock_client_class,
):
	mock_get_single.return_value = _settings()
	mock_get_doc.return_value = _notification()
	delivery = _delivery()
	mock_get_delivery.return_value = delivery
	mock_get_chat_user.return_value = FakeDoc(enabled=0)

	process_notification_log("NOTIF-0001")

	assert delivery.status == "Skipped"
	assert "disabled" in delivery.error.lower()
	mock_client_class.assert_not_called()


@patch("av_tools.google_chat_conversations.notification.GoogleChatClient")
@patch("av_tools.google_chat_conversations.notification._get_or_create_delivery")
@patch("av_tools.google_chat_conversations.notification.frappe.get_doc")
@patch("av_tools.google_chat_conversations.notification.frappe.get_single")
def test_process_is_idempotent_when_delivery_already_sent(
	mock_get_single,
	mock_get_doc,
	mock_get_delivery,
	mock_client_class,
):
	mock_get_single.return_value = _settings()
	mock_get_doc.return_value = _notification()
	mock_get_delivery.return_value = _delivery(status="Sent")

	process_notification_log("NOTIF-0001")

	mock_client_class.assert_not_called()


@patch("av_tools.google_chat_conversations.notification.GoogleChatClient")
@patch("av_tools.google_chat_conversations.notification._get_or_create_chat_user")
@patch("av_tools.google_chat_conversations.notification._get_or_create_delivery")
@patch("av_tools.google_chat_conversations.notification.frappe.get_doc")
@patch("av_tools.google_chat_conversations.notification.frappe.get_single")
def test_google_chat_api_failure_marks_delivery_failed_and_reraises(
	mock_get_single,
	mock_get_doc,
	mock_get_delivery,
	mock_get_chat_user,
	mock_client_class,
):
	mock_get_single.return_value = _settings()
	mock_get_doc.return_value = _notification()
	delivery = _delivery()
	mock_get_delivery.return_value = delivery
	mock_get_chat_user.return_value = FakeDoc(enabled=1)
	client = mock_client_class.return_value
	client.ensure_personal_threaded_space.side_effect = GoogleChatAPIError("HTTP 503")

	with pytest.raises(GoogleChatAPIError, match="503"):
		process_notification_log("NOTIF-0001")

	assert delivery.status == "Failed"
	assert delivery.attempts == 1
	assert "503" in delivery.error


@patch("av_tools.google_chat_conversations.notification.frappe.local")
def test_same_document_reuses_thread_key_across_notifications(mock_local):
	mock_local.site = "erp.example.com"

	first = make_thread_key("Sales Invoice", "SINV-0001")
	second = make_thread_key("Sales Invoice", "SINV-0001")

	assert first == second


@patch("av_tools.google_chat_conversations.notification.frappe.local")
def test_different_documents_get_different_threads(mock_local):
	mock_local.site = "erp.example.com"

	invoice = make_thread_key("Sales Invoice", "SINV-0001")
	payment = make_thread_key("Payment Entry", "PE-0001")

	assert invoice != payment
