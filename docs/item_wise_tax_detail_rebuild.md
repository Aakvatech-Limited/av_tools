# Redo Item-wise Tax Detail

Repairs the derived ERPNext v16 `Item Wise Tax Detail` child table for submitted
Sales Invoices and Purchase Invoices. It is independent of csf_mu and applies to
percentage tax accounts regardless of account name or country. All ordinary
readers subsequently see the repaired records through ERPNext's standard table.
It does not modify the separate, site-stored VAT Pre-Filing Validation report.

## Deploy and use

Merge into `version-16-hotfix`, update the bench, build assets and run
`bench --site SITE migrate`. Reload Desk so the new hooks and scripts load.
No custom roles, Server Scripts, automatic data migration or extra app are added.
ERPNext v16 must be installed on the site when this tool is used.

1. On a submitted Sales/Purchase Invoice, open **Tools > Redo Item-wise Tax Detail**.
   Alternatively use the same button on either invoice list or search for
   **Item Wise Tax Detail Rebuild** in Desk.
2. Select company, transaction type and inclusive posting dates. A single invoice
   is optional; batches default to 100 and are limited to 200 invoices per request.
   Too many matches cause an error instead of silently truncating the selection.
   Selection respects the current user's source document permissions.
3. Save and click **Preview**. Expand each result for the existing records,
   proposed records and reconciliation for every tax account. No source writes
   occur during preview. Status is Ready, Unchanged or Blocked, with reasons.
4. After reviewing, click **Rebuild Ready Invoices** and confirm the count.
   Only the user who previewed can queue that request. Processing runs as that
   user in the long queue; the form polls progress and retains per-invoice results.
5. Reload the invoices and rerun the pre-filing report with the saved-rate fallback
   OFF to verify that the actual stored details now reconcile.

Only Accounts Manager and System Manager can use this maintenance tool, and
source read/write permissions plus company restrictions still apply. Other users
need no new roles to read the corrected invoice data through their normal access.

## Supported reconstruction

- Uses each invoice item's **saved** `item_tax_rate` for the exact tax account.
  An explicit zero stays zero, even when item codes repeat.
- Never fetches today's Item Tax Template rates. If a template is linked but its
  saved account-specific rate is missing, the invoice is blocked. Untemplated
  items may use the rate saved on the invoice's tax row.
- Uses signed `base_net_amount`, preserving credit notes and negative adjustment
  lines; amounts already in base currency are not converted again.
- Supports tax-inclusive prices (`included_in_print_rate = 1`) for the supported
  percentage-on-net charges. ERPNext's saved `base_net_amount` is already net of
  inclusive tax: an inclusive price of 115 at 15% has net 100 and VAT 15. The tool
  uses that saved net; it neither applies 15% to gross 115 nor removes the tax a
  second time. Mixed taxable/exempt items, inclusive credit notes, foreign
  currencies and multiple independent inclusive percentage accounts follow the
  same rule. Wrong/missing saved net values cannot be guessed from today's
  templates; unexplained differences remain blocked.
- Supports On Net Total percentage charges, including simple Deduct rows, and
  works independently for every tax account. Current-template rates, invoice
  totals and GL entries are never recalculated.
- Uses company currency precision. A per-account rounding residual may be applied
  only to a nonzero taxable row, within the requested tolerance (maximum 0.5 in
  base currency). It cannot move tax onto a zero-rate row or reverse a row's sign.
- Whole invoices are blocked for Actual, previous-row, per-quantity, withholding
  or manually frozen tax rows, invoice-level discounts, missing/invalid historical
  rates, unsupported precision or unexplained differences. No partial replacement
  is performed on these invoices. Their preview includes the reason.

A correct child table is Unchanged and is not written. Some legitimate rounding
layouts can differ by small per-item amounts; Preview exposes that change and
checks the account total before applying the deterministic reconstruction.

## Integrity and audit

Requests become immutable after preview. The tool stores before/proposed JSON
and account controls on the request; it keeps these local to the site. Repair
locks the source invoice and verifies both the complete source fingerprint and
recomputed proposal/configuration fingerprint. Changes to source data, current
child details, currency settings or reconstruction logic invalidate the preview.

Replacement deletes only child rows for the exact invoice, doctype and
`item_wise_tax_details` parent field, inserts correctly linked replacement rows,
then reads them back and compares them with the proposal. It never calls invoice
save/submit/cancel, recalculates totals or posts GL entries. Only derived child
records, invoice modified/modified_by metadata, a source Info comment and request
progress/audit records are written. Legacy tax-row JSON is retained unchanged.

Each invoice uses a savepoint. Failure rolls that invoice back, records Failed
and continues with the remaining Ready entries. Successful invoices and their
result are committed together. Overlapping requests serialize on the source
parent lock; stale previews fail rather than overwriting another repair. Repeated
runs of an already corrected invoice are Unchanged.

A killed worker can leave a request Running. Review its per-invoice results and
create a fresh request for remaining invoices; do not rerun the original ERPNext
migration or manually change this request's audit/status. A fresh preview checks
current records and avoids duplicate accumulation.

Existing submitted VAT filings keep their original snapshots; this tool does not
amend filed returns or claim dates. Preview should first be tried on a staging
copy and a small verified set before a production batch.

## Verification

Isolated tests (no bench required):

```bash
python -m unittest av_tools.tax_detail_rebuild.test_calculation av_tools.tax_detail_rebuild.test_service -v
```

The suite uses synthetic values only and covers repeated codes with zero rates,
inclusive prices, signed/credit adjustments, FX, rounding, multiple accounts, exclusions, permissions,
stale source/proposal checks, repeated runs and per-invoice rollback boundaries.
These checks use mocked Frappe persistence, not a live database.

On a Frappe v16 test site additionally verify DocType synchronization, request
immutability, user/company restrictions, preview with no source writes, the
background job as requester, before/after child data, readback precision, parallel
requests and rollback after an insertion failure. Compare all invoice financial
fields and GL entries before and after, and verify invoice-list/form buttons.
