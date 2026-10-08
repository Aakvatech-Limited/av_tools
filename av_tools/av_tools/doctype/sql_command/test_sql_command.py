# Copyright (c) 2021, Aakvatech and Contributors
# See license.txt

from unittest.mock import call, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSQLCommand(FrappeTestCase):
	def _document(self, **kwargs):
		return frappe.get_doc(
			{
				"doctype": "SQL Command",
				"doctype_name": "ToDo",
				"names": "'TEST-1','TEST-2'",
				**kwargs,
			}
		)

	def test_on_submit_deletes_with_document_api(self):
		doc = self._document()
		with (
			patch.object(frappe.session, "user", "Administrator"),
			patch("frappe.db.get_single_value", return_value=1),
			patch("frappe.get_meta") as meta,
			patch("frappe.delete_doc") as delete_doc,
		):
			meta.return_value.issingle = 0
			meta.return_value.istable = 0
			meta.return_value.is_virtual = 0
			doc.on_submit()

		delete_doc.assert_has_calls(
			[
				call("ToDo", "TEST-1", ignore_permissions=False),
				call("ToDo", "TEST-2", ignore_permissions=False),
			]
		)
		self.assertEqual(delete_doc.call_count, 2)

	def test_sql_text_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._document(sql_text="SELECT * FROM tabUser").on_submit()

	def test_non_administrator_cannot_delete(self):
		with patch.object(frappe.session, "user", "user@example.com"):
			with self.assertRaises(frappe.PermissionError):
				self._document().on_submit()

	def test_unquoted_names_are_rejected(self):
		doc = self._document(names="TEST-1,TEST-2")
		with (
			patch.object(frappe.session, "user", "Administrator"),
			patch("frappe.db.get_single_value", return_value=1),
			patch("frappe.get_meta") as meta,
		):
			meta.return_value.issingle = 0
			meta.return_value.istable = 0
			meta.return_value.is_virtual = 0
			with self.assertRaises(frappe.ValidationError):
				doc.on_submit()
