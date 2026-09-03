from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from av_tools.google_chat_conversations.api import GoogleChatAPIError, GoogleChatClient


class FakeChatUser(SimpleNamespace):
	def db_set(self, fieldname, value, update_modified=False):
		setattr(self, fieldname, value)


def _settings(**overrides):
	values = {
		"request_timeout": 15,
		"personal_space_prefix": "ERPNext Notifications",
		"workspace_customer": "customers/my_customer",
	}
	values.update(overrides)
	return SimpleNamespace(**values)


def _response(status_code=200, payload=None, text=""):
	response = MagicMock()
	response.status_code = status_code
	response.text = text
	response.content = b"{}" if payload is not None else b""
	response.json.return_value = payload or {}
	return response


@patch.object(GoogleChatClient, "_get_access_token", return_value="token-123")
@patch("av_tools.google_chat_conversations.api.requests.request")
def test_request_sends_bearer_token_and_returns_mocked_json(mock_request, mock_token):
	mock_request.return_value = _response(payload={"name": "spaces/AAA/messages/MSG1"})
	client = GoogleChatClient(_settings())

	result = client._request("GET", "spaces/AAA")

	assert result["name"] == "spaces/AAA/messages/MSG1"
	mock_request.assert_called_once()
	kwargs = mock_request.call_args.kwargs
	assert kwargs["headers"]["Authorization"] == "Bearer token-123"
	assert kwargs["timeout"] == 15


@patch.object(GoogleChatClient, "_get_access_token", return_value="token-123")
@patch("av_tools.google_chat_conversations.api.requests.request")
def test_request_raises_google_chat_error_for_http_failure(mock_request, mock_token):
	mock_request.return_value = _response(status_code=503, payload={}, text="service unavailable")
	client = GoogleChatClient(_settings())

	with pytest.raises(GoogleChatAPIError, match="503"):
		client._request("POST", "spaces/AAA/messages", json_body={"text": "hello"})


@patch.object(GoogleChatClient, "_get_access_token", return_value="token-123")
@patch("av_tools.google_chat_conversations.api.requests.request")
def test_request_wraps_network_failure(mock_request, mock_token):
	mock_request.side_effect = requests.ConnectionError("network down")
	client = GoogleChatClient(_settings())

	with pytest.raises(GoogleChatAPIError, match="network down"):
		client._request("GET", "spaces/AAA")


@patch.object(GoogleChatClient, "_request")
@patch("av_tools.google_chat_conversations.api.frappe.local")
def test_personal_threaded_space_creates_space_then_membership(mock_local, mock_request):
	mock_local.site = "erp.example.com"
	mock_request.side_effect = [
		{"name": "spaces/AAA"},
		{"name": "spaces/AAA/members/USER1"},
	]
	chat_user = FakeChatUser(
		user="user@example.com",
		google_email="user@example.com",
		personal_space_name=None,
		personal_space_display_name=None,
	)
	client = GoogleChatClient(_settings())

	space = client.ensure_personal_threaded_space(chat_user)

	assert space == "spaces/AAA"
	assert chat_user.personal_space_name == "spaces/AAA"
	assert chat_user.personal_space_display_name == "ERPNext Notifications - user@example.com"
	assert mock_request.call_count == 2
	create_call = mock_request.call_args_list[0]
	assert create_call.args[0:2] == ("POST", "spaces")
	assert create_call.kwargs["json_body"]["spaceType"] == "SPACE"
	membership_call = mock_request.call_args_list[1]
	assert membership_call.args[0:2] == ("POST", "spaces/AAA/members")
	assert membership_call.kwargs["json_body"]["member"]["name"] == "users/user@example.com"
	assert membership_call.kwargs["allow_statuses"] == {409}


@patch.object(GoogleChatClient, "_request")
def test_existing_personal_space_is_reused_without_api_call(mock_request):
	chat_user = FakeChatUser(
		user="user@example.com",
		google_email="user@example.com",
		personal_space_name="spaces/EXISTING",
		personal_space_display_name="ERPNext Notifications",
	)
	client = GoogleChatClient(_settings())

	assert client.ensure_personal_threaded_space(chat_user) == "spaces/EXISTING"
	mock_request.assert_not_called()


@patch.object(GoogleChatClient, "_request")
def test_find_direct_message_uses_google_user_id_and_caches_space(mock_request):
	mock_request.return_value = {"name": "spaces/DM1"}
	chat_user = FakeChatUser(
		google_chat_user_id="123456789",
		direct_message_space_name=None,
	)
	client = GoogleChatClient(_settings())

	space = client.find_direct_message(chat_user)

	assert space == "spaces/DM1"
	assert chat_user.direct_message_space_name == "spaces/DM1"
	mock_request.assert_called_once_with(
		"GET",
		"spaces:findDirectMessage",
		params={"name": "users/123456789"},
	)


def test_find_direct_message_requires_google_user_id():
	chat_user = FakeChatUser(google_chat_user_id=None, direct_message_space_name=None)
	client = GoogleChatClient(_settings())

	with pytest.raises(GoogleChatAPIError, match="Google Chat User ID"):
		client.find_direct_message(chat_user)


@patch.object(GoogleChatClient, "_request")
def test_send_threaded_message_uses_thread_key_and_reply_fallback(mock_request):
	mock_request.return_value = {
		"name": "spaces/AAA/messages/MSG1",
		"thread": {"name": "spaces/AAA/threads/THREAD1"},
	}
	client = GoogleChatClient(_settings())

	result = client.send_message(
		"spaces/AAA",
		"Payment Entry notification",
		"request-1",
		thread_key="erpnext-thread-1",
	)

	assert result["thread"]["name"] == "spaces/AAA/threads/THREAD1"
	mock_request.assert_called_once_with(
		"POST",
		"spaces/AAA/messages",
		params={
			"requestId": "request-1",
			"messageReplyOption": "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD",
		},
		json_body={
			"text": "Payment Entry notification",
			"thread": {"threadKey": "erpnext-thread-1"},
		},
	)


@patch.object(GoogleChatClient, "_request")
def test_send_direct_message_omits_thread_fields(mock_request):
	mock_request.return_value = {"name": "spaces/DM1/messages/MSG1"}
	client = GoogleChatClient(_settings())

	client.send_message("spaces/DM1", "hello", "request-2")

	mock_request.assert_called_once_with(
		"POST",
		"spaces/DM1/messages",
		params={"requestId": "request-2"},
		json_body={"text": "hello"},
	)
