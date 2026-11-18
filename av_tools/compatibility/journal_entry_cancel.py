"""Compatibility for ERPNext v16 Journal Entry cancellation.

ERPNext 16.55.0 concatenates a tuple of ignored linked DocTypes with a list
populated by AccountsController.on_cancel(), raising TypeError. This mixin
preserves the upstream cancellation sequence while normalizing that collection.

Remove this extension after upgrading to an ERPNext release with the fix.
"""

from erpnext.accounts.doctype.journal_entry.journal_entry import JournalEntry
from erpnext.accounts.doctype.tax_withholding_entry.tax_withholding_entry import JournalTaxWithholding


class JournalEntryCancellationCompatibility:
	"""Work around tuple + list in ERPNext's JournalEntry.on_cancel()."""

	def on_cancel(self):
		# Deliberately skip only JournalEntry.on_cancel(), whose tuple + list
		# operation fails. Run its parent controller's cancellation unchanged.
		super(JournalEntry, self).on_cancel()

		from_doc_events = getattr(self, "ignore_linked_doctypes", ()) or ()
		self.ignore_linked_doctypes = (
			"GL Entry",
			"Stock Ledger Entry",
			"Payment Ledger Entry",
			"Repost Payment Ledger",
			"Repost Payment Ledger Items",
			"Repost Accounting Ledger",
			"Repost Accounting Ledger Items",
			"Unreconcile Payment",
			"Unreconcile Payment Entries",
			"Advance Payment Ledger Entry",
			"Tax Withholding Entry",
		)

		if from_doc_events and from_doc_events != self.ignore_linked_doctypes:
			self.ignore_linked_doctypes += tuple(from_doc_events)

		# Keep every post-parent operation in upstream JournalEntry.on_cancel().
		self.make_gl_entries(1)
		JournalTaxWithholding(self).on_cancel()
		self.unlink_advance_entry_reference()
		self.unlink_asset_reference()
		self.unlink_inter_company_jv()
		self.unlink_asset_adjustment_entry()
		self.update_invoice_discounting()
		self.update_payment_order_requests(cancel=True)
