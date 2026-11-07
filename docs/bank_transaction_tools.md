# Bank Transaction tools

## Deployment

Merge the single feature PR into `version-16-hotfix`, update the bench, build assets,
and run `bench --site SITE migrate`. Reload the Bank Transaction list in the browser.
No Server Script setting, extra app or custom role is required.

The pre-sync patch adopts an existing custom **Bank Transaction GL Generation**
DocType as a standard Av Tools DocType, preserving its records and names. It also
adopts the existing **Bank Transaction Statement** Report. Finish queued/running
prototype jobs before migration; a pending legacy API call must not be orphaned.

The post-sync patch creates/updates the same four Bank Transaction custom fields,
loads the native report, and disables only these prototype records:

- Bank Transaction GL Generation - Validate Request
- Bank Transaction GL Generation - Worker
- Bank Transaction GL Generation - Queue
- Bank Transaction - Validate GL Source
- Bank Transaction - Release GL Source on Cancel
- Bank Transaction - Release GL Source on Discard
- Bank Transaction - Require Live GL Generation
- Bank Transaction - Generate from GL Entries (Client Script)
- Bank Transaction GL Generation - Progress (Client Script)

Disabled scripts remain available as reference. Unrelated scripts and existing
Bank Transactions are preserved. Setup is idempotent, including on a fresh install.
Do not manually re-enable the prototype scripts after migration.

## Rules

- One draft per GL Entry; no grouping or netting of split rows.
- Use debit/credit in account currency, never company-currency amounts for a
  foreign-currency bank account. Zero, negative and two-sided rows are skipped.
- The posting date must fall within the requested dates; the cut-off is inclusive.
- The voucher must be submitted and support ERPNext bank reconciliation.
- Skip opening entries, cancelled entries, unsupported vouchers, and ambiguous
  bank-account mappings. The result log records why each item was skipped.
- Duplicate checks consider active drafts and submitted Bank Transactions on the
  same bank GL account. Untagged voucher links block the voucher; identified GL
  links block only that individual GL row. Cancelled/discarded records do not block.
- Draft payment links start with zero allocation. Submission invokes ERPNext's
  allocation and clearance logic and rechecks the source and existing reservations.
- Runs execute as their requester, with normal create and read permissions. A bank
  row lock serializes overlapping runs; the unique active source key prevents the
  same GL row from being inserted twice concurrently.
- The job commits all created drafts together. A failed run rolls them all back and
  keeps a failure log. Preview validates eligibility without inserting anything.

## Validation

Run the isolated suite without a bench:

```bash
python -m unittest av_tools.banking.test_banking -v
```

Before a production generation, run Preview Only on a known range. On a test site,
check two GL rows from the same voucher, an internal transfer (separate banks), a
voucher already linked to an imported transaction, a repeated run, concurrent runs,
and a user restricted to one company. Confirm source links, currency, draft status,
zero allocations, cut-off enforcement and standard reconciliation on submission.
Compare report detail and monthly closing balances, including a month without
transactions and a range spanning December/January. The isolated suite exercises
financial rules and failure handling; database migration and live submission also
need this bench validation.
