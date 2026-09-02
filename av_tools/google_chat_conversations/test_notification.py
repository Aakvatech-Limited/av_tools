from types import SimpleNamespace
from unittest.mock import patch

from av_tools.google_chat_conversations.notification import format_notification_message, make_thread_key


def test_format_notification_message_strips_html():
	notification = SimpleNamespace(
		subject="<strong>You</strong> gained <strong>3</strong> points",
		document_type="Payment Entry",
		document_name="PE-2026-05100",
		type="Energy Point",
	)
	settings = SimpleNamespace(include_document_link=0)

	message = format_notification_message(notification, settings)

	assert "<strong>" not in message
	assert "You gained 3 points" in message
	assert "Payment Entry: PE-2026-05100" in message
	assert "Notification: Energy Point" in message


@patch("av_tools.google_chat_conversations.notification.frappe.local")
def test_thread_key_is_deterministic(mock_local):
	mock_local.site = "erp.example.com"

	first = make_thread_key("Payment Entry", "PE-2026-05100")
	second = make_thread_key("Payment Entry", "PE-2026-05100")

	assert first == second
	assert first.startswith("erpnext-")
