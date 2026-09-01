# Copyright (c) 2020, Aakvatech and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools.doctype.visibility.visibility import get_doc_fields


class TestVisibility(FrappeTestCase):
	def test_get_doc_fields_returns_supported_party_links(self):
		fields = get_doc_fields("Sales Order")

		self.assertTrue(any(field["fieldname"] == "customer" for field in fields))
