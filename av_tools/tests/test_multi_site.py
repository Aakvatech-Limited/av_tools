# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests import IntegrationTestCase

from av_tools.api.multi_site_orchestrator import (
	_disable_user_on_site,
	disable_user_on_all_sites,
	enable_user_on_all_sites,
	update_site_configuration,
)


def response(status, text="ok"):
	mock = MagicMock()
	mock.status_code = status
	mock.text = text
	return mock


class TestMultiSiteOrchestrator(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("Site Configuration", "AV Test Sites"):
			frappe.delete_doc("Site Configuration", "AV Test Sites", force=1)
		self.config = frappe.get_doc(
			{
				"doctype": "Site Configuration",
				"title": "AV Test Sites",
				"sites": [
					{
						"enabled": 1,
						"site_name": "one",
						"site_url": "one.example.com",
						"api_key": "k",
						"api_secret": "s",
					},
					{
						"enabled": 0,
						"site_name": "two",
						"site_url": "https://two.example.com/",
						"api_key": "k",
						"api_secret": "s",
					},
				],
			}
		).insert()

	def test_validation(self):
		self.assertRaises(frappe.ValidationError, disable_user_on_all_sites, "", self.config.name)
		self.assertRaises(frappe.ValidationError, enable_user_on_all_sites, "u@example.com", "")

	def test_disable_and_enable_across_sites(self):
		with patch("av_tools.api.multi_site_orchestrator.requests.put", return_value=response(200)) as put:
			result = disable_user_on_all_sites("u@example.com", self.config.name)
		self.assertEqual(result["total_sites"], 2)
		self.assertEqual(result["enabled_sites"], 1)
		self.assertEqual([r["status"] for r in result["results"]], ["success", "skipped"])
		self.assertEqual(put.call_args[0][0], "https://one.example.com/api/resource/User/u@example.com")
		self.assertEqual(put.call_args[1]["json"], {"enabled": 0})
		self.assertEqual(put.call_args[1]["headers"]["Authorization"], "token k:s")

		with patch("av_tools.api.multi_site_orchestrator.requests.put", return_value=response(404)):
			result = enable_user_on_all_sites("u@example.com", self.config.name)
		self.assertEqual(result["action"], "enable")
		self.assertIn("does not exist", result["results"][0]["message"])

	def test_error_mapping(self):
		for status, fragment in (
			(403, "Permission denied"),
			(401, "Authentication failed"),
			(500, "HTTP 500"),
		):
			with patch(
				"av_tools.api.multi_site_orchestrator.requests.put", return_value=response(status, "boom")
			):
				self.assertIn(
					fragment,
					_disable_user_on_site("u@example.com", "one", "one.example.com", "k", "s")["message"],
				)
		for error, fragment in (
			(requests.exceptions.Timeout(), "Timeout"),
			(requests.exceptions.ConnectionError(), "Connection failed"),
			(RuntimeError("x"), "Exception"),
		):
			with patch("av_tools.api.multi_site_orchestrator.requests.put", side_effect=error):
				self.assertIn(
					fragment,
					_disable_user_on_site("u@example.com", "one", "one.example.com", "k", "s")["message"],
				)

	def test_update_site_configuration_replaces_children(self):
		payload = {
			"name": self.config.name,
			"title": "AV Test Sites",
			"description": "updated",
			"sites": [
				{
					"enabled": 1,
					"site_name": "three",
					"site_url": "three.example.com",
					"api_key": "k",
					"api_secret": "s",
				}
			],
		}
		updated = update_site_configuration(frappe.as_json(payload))
		self.assertEqual(updated.description, "updated")
		self.assertEqual([s.site_name for s in updated.sites], ["three"])

	def test_requires_system_manager(self):
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")
		self.assertRaises(
			frappe.PermissionError, disable_user_on_all_sites, "u@example.com", self.config.name
		)
