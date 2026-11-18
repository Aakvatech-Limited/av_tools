"""Regression tests for ERPNext v16 Journal Entry cancellation compatibility."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from av_tools.compatibility.journal_entry_cancel import JournalEntryCancellationCompatibility
from erpnext.accounts.doctype.journal_entry.journal_entry import JournalEntry


class TestJournalEntryCancellationCompatibility(FrappeTestCase):
	def test_controller_extension_is_active(self):
		controller = frappe.get_controller("Journal Entry")
		self.assertTrue(issubclass(controller, JournalEntryCancellationCompatibility))

	def test_preserves_parent_events_and_cancel_operations_with_list(self):
		controller = frappe.get_controller("Journal Entry")
		journal = controller.__new__(controller)
		journal.doctype = "Journal Entry"
		journal.name = "TEST-JE-CANCELLATION"

		calls = []

		def parent_cancel(_self):
			calls.append("parent_cancel")
			_self.ignore_linked_doctypes = ["Payment Entry"]

		with (
			patch.object(JournalEntry.__mro__[1], "on_cancel", parent_cancel),
			patch("av_tools.compatibility.journal_entry_cancel.JournalTaxWithholding") as withholding,
			patch.object(controller, "make_gl_entries", lambda self, cancel: calls.append(("gl", cancel))),
			patch.object(controller, "unlink_advance_entry_reference", lambda self: calls.append("advance")),
			patch.object(controller, "unlink_asset_reference", lambda self: calls.append("asset")),
			patch.object(controller, "unlink_inter_company_jv", lambda self: calls.append("intercompany")),
			patch.object(controller, "unlink_asset_adjustment_entry", lambda self: calls.append("asset_adjustment")),
			patch.object(controller, "update_invoice_discounting", lambda self: calls.append("discounting")),
			patch.object(controller, "update_payment_order_requests", lambda self, cancel: calls.append(("payment_order", cancel))),
		):
			journal.on_cancel()

		self.assertEqual(calls[0], "parent_cancel")
		self.assertEqual(calls[1], ("gl", 1))
		self.assertIn("Payment Entry", journal.ignore_linked_doctypes)
		self.assertIn("GL Entry", journal.ignore_linked_doctypes)
		self.assertEqual(journal.ignore_linked_doctypes.count("Payment Entry"), 1)
		self.assertEqual(calls[-1], ("payment_order", True))
		withholding.assert_called_once_with(journal)
		withholding.return_value.on_cancel.assert_called_once()
