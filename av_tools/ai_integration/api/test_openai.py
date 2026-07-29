# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from av_tools.ai_integration.api.openai import analyze_doctype_with_openai
from av_tools.patches.v1_0.migrate_ai_integration_site_data import (
	APP_NAME,
	MODULE_NAME,
	execute as migrate_ai_integration_site_data,
)


class TestOpenAI(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def test_analyze_doctype_with_openai_returns_cached_response(self):
		prompt = f"Explain ToDo {frappe.generate_hash(length=8)}"
		expected_response = "Cached analysis"

		frappe.get_doc(
			{
				"doctype": "OpenAI Query Log",
				"doctype_name": "ToDo",
				"query": prompt,
				"response": expected_response,
				"status": "Complete",
				"resend_count": 1,
			}
		).insert()

		with patch("frappe.enqueue") as mock_enqueue:
			response = analyze_doctype_with_openai("ToDo", prompt)

		self.assertEqual(response, expected_response)
		mock_enqueue.assert_not_called()

	def test_analyze_doctype_with_openai_force_resend_increments_counter(self):
		prompt = f"Explain ToDo {frappe.generate_hash(length=8)}"

		frappe.get_doc(
			{
				"doctype": "OpenAI Query Log",
				"doctype_name": "ToDo",
				"query": prompt,
				"response": "Old analysis",
				"status": "Complete",
				"resend_count": 1,
			}
		).insert()

		with patch("frappe.enqueue") as mock_enqueue:
			response = analyze_doctype_with_openai("ToDo", prompt, force_resend=True)

		self.assertIn("Queued", response)
		logs = frappe.get_all(
			"OpenAI Query Log",
			filters={"doctype_name": "ToDo", "query": prompt},
			fields=["name", "resend_count", "status"],
			order_by="creation asc",
		)
		self.assertEqual(len(logs), 2)
		self.assertEqual(logs[-1].status, "Queued")
		self.assertEqual(logs[-1].resend_count, 2)
		mock_enqueue.assert_called_once()

	def test_patch_reassigns_ai_integration_module_to_av_tools(self):
		if not frappe.db.exists("Module Def", MODULE_NAME):
			self.skipTest(f"{MODULE_NAME} module is not available on this site")

		frappe.db.set_value("Module Def", MODULE_NAME, "app_name", "csf_tz", update_modified=False)

		migrate_ai_integration_site_data()

		self.assertEqual(frappe.db.get_value("Module Def", MODULE_NAME, "app_name"), APP_NAME)
