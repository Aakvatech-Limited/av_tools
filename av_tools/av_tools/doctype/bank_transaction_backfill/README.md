# Bank Transaction Backfill

Use **Bank Transaction Backfill** to create missing submitted Bank Transactions from already-cleared ERPNext vouchers.

## Procedure

1. Create a new **Bank Transaction Backfill** document.
2. Select **Company**, **Source DocType** (loaded from the site bank reconciliation registry), and the inclusive **clearance-date range**.
3. Save the draft, then click **Preview Eligible Transactions**.
4. Review the candidate table, including bank accounts, deposit/withdrawal amounts and dates. The preview will be saved.
5. **Submit** the backfill. Each candidate is revalidated against its source voucher and bank GL entries before the Bank Transaction is created and submitted.

## Controls

- Requires **Accounts Manager** or **System Manager** permission on the backfill.
- At most 200 source vouchers per run; narrow the clearance-date range for larger histories.
- Only submitted source documents with a clearance date are included.
- Skips sources already referenced by noncancelled Bank Transactions, including drafts.
- Resolves a bank account only where exactly one ERPNext Bank Account maps to the underlying ledger account within the selected company.
- Uses bank GL entries to derive deposit/withdrawal amounts, including multiple bank accounts on a Journal Entry.
- Each entry has its own savepoint: failures are recorded without rolling back successful entries.
- A backfill submission cannot be cancelled; to rerun, create another backfill. Existing Bank Transactions are not deleted or altered by this tool.
- **This operation does not import bank statements**; Bank Transactions are synthesized from accounting vouchers and their clearance dates. Inspect the resulting transactions and any bank statement reconciliation implications before using on production data.

## Limitations

- Missing or ambiguous Bank Account mappings are not fabricated and those vouchers do not appear in the preview.
- Vouchers with existing allocations are excluded, including partially allocated vouchers. This tool is not for repairing partially reconciled payments.
- Dates are filtered on the source voucher **clearance date**, not its posting date.
- Execute first on a staging copy and compare bank transaction totals to bank statement balances.

## Source compatibility

- Source DocType options come from `frappe.get_hooks("bank_reconciliation_doctypes")`, including Doctypes contributed by installed apps.
- Payment Entry, Journal Entry and paid Purchase Invoice use the parent `clearance_date` field.
- POS Sales Invoice uses `Sales Invoice Payment.clearance_date`. Multiple payment rows with conflicting clearance dates cannot be safely collapsed and are excluded.
- Additional registered source types must expose `company` and `clearance_date`; bank GL entries must resolve to exactly one Bank Account. Sources without this common structure are refused rather than being silently processed.

## Reconciliation outcomes

After Bank Transaction submission, the backfill reads its persisted status and allocated/unallocated amounts.

- **Created** / parent **Fully Reconciled**: submitted, status Reconciled, fully allocated and no remainder.
- **Partially Reconciled**: submitted, some amount allocated and a positive unallocated balance remains.
- **Unreconciled**: submitted but no meaningful allocation, or not confirmed as fully reconciled.
- **Skipped**: no longer eligible; **Failed**: creation/submission error.

The resulting Bank Transaction remains linked to the backfill row, including for partially reconciled or unreconciled transactions.
