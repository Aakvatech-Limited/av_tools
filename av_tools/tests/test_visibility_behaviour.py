# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from av_tools.av_tools.doctype.visibility.visibility import (
	get_doc_fields,
	get_documents_for_today,
	run_visibility,
	trigger_daily_alerts,
)


class TestVisibilityBehaviour(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.cache.hdel, "vis_notifications", "ToDo")

	def make_alert(self, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Visibility",
				"subject": values.pop("subject", f"AV Test Alert {frappe.generate_hash(length=5)}"),
				"document_type": "ToDo",
				"event": "Save",
				"enabled": 1,
				"set_property_after_alert": "status",
				"property_value": "Closed",
				**values,
			}
		)
		return doc.insert()

	def test_validation_rules(self):
		self.assertRaises(frappe.ValidationError, self.make_alert, event="Days Before")
		self.assertRaises(frappe.ValidationError, self.make_alert, event="Value Change")
		self.assertRaises(frappe.ValidationError, self.make_alert, condition="doc.this is not python")
		self.assertRaises(frappe.ValidationError, self.make_alert, document_type="Approver Detail")
		alert = self.make_alert(condition="doc.description == 'trigger'")
		self.assertEqual(alert.name, alert.subject)

	def test_save_event_sets_property(self):
		self.make_alert(condition="doc.description == 'trigger'")
		with patch("frappe.db.commit"):
			todo = frappe.get_doc({"doctype": "ToDo", "description": "trigger"}).insert()
			other = frappe.get_doc({"doctype": "ToDo", "description": "quiet"}).insert()
		self.assertEqual(frappe.db.get_value("ToDo", todo.name, "status"), "Closed")
		self.assertEqual(frappe.db.get_value("ToDo", other.name, "status"), "Open")

	def test_run_visibility_is_skipped_during_patch(self):
		self.make_alert(condition="doc.description == 'trigger'")
		todo = frappe.new_doc("ToDo")
		todo.description = "trigger"
		frappe.flags.in_patch = True
		try:
			self.assertIsNone(run_visibility(todo, "on_update"))
		finally:
			frappe.flags.in_patch = False
		self.assertIsNone(todo.flags.vis_notifications)

	def test_days_before_alert_finds_documents(self):
		alert = self.make_alert(event="Days Before", date_changed="date", days_in_advance=0)
		with patch("frappe.db.commit"):
			todo = frappe.get_doc({"doctype": "ToDo", "description": "dated", "date": nowdate()}).insert()
		self.assertIn(todo.name, get_documents_for_today(alert.name))
		with patch("frappe.db.commit"):
			trigger_daily_alerts()
		self.assertEqual(frappe.db.get_value("ToDo", todo.name, "status"), "Closed")

	def test_value_change_event(self):
		self.make_alert(
			event="Value Change", value_changed="description", condition="doc.description == 'changed'"
		)
		with patch("frappe.db.commit"):
			todo = frappe.get_doc({"doctype": "ToDo", "description": "original"}).insert()
			self.assertEqual(frappe.db.get_value("ToDo", todo.name, "status"), "Open")
			todo.description = "changed"
			todo.save()
		self.assertEqual(frappe.db.get_value("ToDo", todo.name, "status"), "Closed")

	def test_get_doc_fields(self):
		fields = get_doc_fields("Sales Invoice")
		self.assertTrue(any(f["fieldname"] == "customer" for f in fields))
		self.assertEqual(get_doc_fields("Role"), [])
