# ERPNext v16 Journal Entry cancellation compatibility

ERPNext 16.55.0 has a tuple/list concatenation error in
`JournalEntry.on_cancel()` when `AccountsController.on_cancel()`
populates `ignore_linked_doctypes` as a list.

`av_tools.compatibility.journal_entry_cancel.JournalEntryCancellationCompatibility`
is registered using Frappe's `extend_doctype_class` hook for Journal Entry.
It executes the original parent controller's cancellation and the remaining
upstream Journal Entry cancellation operations, changing only the concatenation
to `tuple(from_doc_events)`.

This is an ERPNext-version-specific workaround and must be compared against
the upstream `JournalEntry.on_cancel()` implementation before upgrading ERPNext.
Remove the extension once the upstream fix is present; never leave two divergent
cancellation implementations indefinitely.

## Regression / UAT

- Run `bench --site <test-site> run-tests --app av_tools --module av_tools.compatibility.test_journal_entry_cancel`.
- Cancel a submitted system-generated Credit Note linked to an invoice in a test site.
- Confirm both JE and SI are cancelled; GL, Payment Ledger and outstanding
  balances remain consistent; test normal JE and debit-note paths.
- Confirm the original submitted documents on production are unchanged until
  deployment and authorization for cancellation.

Incident example: `ACC-SINV-2026-49799` and `ACC-JV-2026-00644`.
No data correction or automated production cancellation is part of this patch.

## Navigation and analytics

This is a controller compatibility bug fix, not a business feature. Existing
Dock, Sidebar, Workspace, Number Cards, Dashboard Charts and Dashboards remain
unchanged and need no new artifacts.
