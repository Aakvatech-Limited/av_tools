# Copyright (c) 2021, Aakvatech and Contributors
# See license.txt

from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestBackgroundDocumentPosting(FrappeTestCase):
	def test_on_submit_queues_requested_action(self):
		doc = frappe.get_doc(
			{
				"doctype": "Background Document Posting",
				"document_type": "ToDo",
				"document_name": "TEST-TODO",
				"posting_type": "submit",
				"timeout": 1200,
			}
		)
		target_doc = Mock()

		with patch("frappe.get_doc", return_value=target_doc):
			doc.on_submit()

		target_doc.queue_action.assert_called_once_with("submit", timeout=1200)
