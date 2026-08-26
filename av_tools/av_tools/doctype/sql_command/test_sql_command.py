# Copyright (c) 2021, Aakvatech and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


class TestSQLCommand(IntegrationTestCase):
	def test_on_submit_deletes_selected_documents_when_allowed(self):
		doc = frappe.get_doc(
			{
				"doctype": "SQL Command",
				"doctype_name": "ToDo",
				"names": "'TEST-1','TEST-2'",
			}
		)

		with patch("frappe.db.get_single_value", return_value=1), patch("frappe.db.sql") as mock_sql:
			doc.on_submit()

		# v16: document hooks must not commit; the runner's transaction owns the commit
		mock_sql.assert_called_once_with("DELETE FROM `tabToDo` WHERE NAME IN ('TEST-1','TEST-2')")
