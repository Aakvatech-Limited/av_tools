# Asset financial and capitalization reconciliation

This feature packages the AakvaERP customizations inspected on 18 October 2026. It ships three standard DocTypes, the Fixed Asset Financial Reconciliation report, reconciliation form behavior, and the Asset Accounting Audit dialog. No production records were changed during development.

## Behavior

- Reconciliation documents retain the existing field names, parent and child names, amounts, status, dates and remarks. Approval validation now also runs on the server: totals must balance within 0.01, allocations must be non-zero, references must be submitted and in the same company, and source lines/GL entries must belong to the selected voucher.
- The report retains All Records and Exceptions Only views, the live tolerance of 1 company-currency unit, approved balanced mappings, direct submitted Purchase Invoice item coverage, fixed-asset line eligibility, and sortable reference dates. Scrapped Assets, their directly referenced depreciation GL, and scrap Journal Entries are excluded using the current Asset status, including when viewing an earlier as-on date.
- Accounting Audit reads up to 500 uncancelled GL Entries directly referencing the Asset, with company and reference-type filters. Totals describe the displayed entries. It does not infer attribution for shared acquisition vouchers.
- Asset, Purchase Invoice and Journal Entry have native Connections to reconciliation documents. Hooks append the connection and retain existing transactions, internal links and field mappings. Two hidden, server-derived Link fields in the source child table make invoice and journal counts/list filters unambiguous; no capitalization-link buttons are shipped.
- APIs are `av_tools.asset_reconciliation.api.asset_accounting_audit` and `av_tools.asset_reconciliation.api.asset_capitalization_reconciliation_links`. Both require an authenticated caller, enforce document permissions, and run under Frappe v16's read-only decorator. The links API uses permission-filtered parent queries with child filters, with no 500-document scan limit.
- The report scopes every data query by permission-filtered document names. Child reads are constrained to accessible parents and their table fields; required field permissions are checked before querying. Report results therefore describe the caller's accessible records, not an assurance about hidden records. Users need read access to the participating accounting and reconciliation DocTypes. Standard reconciliation edit rights remain System Manager, matching the live definition. Configure additional rights through Role Permission Manager.

## Migration and deployment

1. Back up database and files, and rehearse on a restored **staging** copy of the site.
2. Deploy this branch and run `bench --site <staging-site> migrate`, then build assets and clear browser cache normally.
3. The pre-model-sync patch adopts the existing custom DocTypes in place, retaining their table names. It preserves existing reconciliation permissions as Custom DocPerm and existing custom report roles as Custom Role when no override exists. Fresh installations also adopt existing custom definitions before model sync through the install hook.
4. The post-model-sync patch loads the standard controllers, backfills only the two derived connection fields, converts the report to standard app execution, and disables the exact five feature Client Scripts and two Server Scripts discovered live. Script records and their bodies are retained. Unrelated scripts are untouched. These patches can be rerun safely; no allocation parents are saved or revalidated, and no accounting records are created, submitted, amended or cancelled.
5. Compare reconciliation parent/child record counts, names and allocation totals before and after migration. Compare All Records/Exceptions Only output for the same company/date as an authorized accounting user. Check a mapped Asset, direct invoice capitalization, mixed service/asset invoice, incomplete mapping, and a scrapped Asset with scrap JE.
6. Open Asset, Purchase Invoice and Journal Entry Connections. Check distinct reconciliation counts and filtered list navigation with multiple child rows, other pre-existing connections, and a restricted user. Check the audit dialog, line picker, totals after row deletion, and approval through both the form and API/import paths.
7. Run the integration tests below before production deployment. Production deployment is a separate operation; this PR does not deploy or migrate the live site.

The old short Server Script API names are retired. The bundled UI calls the qualified Python APIs. Any external caller of the short names must switch during deployment. Rollback requires a coordinated code/database restore, or an explicit administrator-reviewed reversal of metadata ownership and script enablement; checking out old code alone is insufficient after migration.

## Purchase Invoice creation for no-time-appropriation

The business workaround treats newly purchased assets as **Existing Asset** records so a full annual depreciation allowance can start at fiscal-year end even when the actual invoice is issued during the year. In **AV Tools Settings**, enable **Create Fiscal-Year Existing Asset Drafts on Purchase Invoice Submit** and configure depreciation method, frequency in months, duration in years, optional Finance Book, and the rate when using Written Down Value. The setting is off by default. Defaults offered are Straight Line, 12 months and 5 years; Finance must confirm the appropriate values before enabling it. Number of periods is duration × 12 ÷ frequency, which must be a positive whole number. Use 12 months for annual postings.

When an ordinary Purchase Invoice is submitted:

- Each enabled non-stock fixed-asset Item line creates one **draft** Asset per whole line quantity. UOM conversion must be 1. Repeated lines are tracked separately. Non-fixed-asset lines and purchase returns create no Assets. Non-depreciable categories produce drafts with depreciation disabled; composite components require the standard capitalization process.
- The invoice posting date and company determine the fiscal year, including non-calendar years. Asset purchase and available-for-use dates use that year's first day; the first depreciation posting date uses its last day. The actual invoice dates are unchanged. Opening accumulated depreciation and booked periods start at zero, with daily pro-rata disabled.
- Each Asset has quantity 1. Cost follows ERPNext's company-currency valuation-rate basis, falling back to base net line amount when valuation rate is unset. Rounding is distributed across the units so their total equals the rounded line cost. Location, Item category, supplier, and accounting dimensions are retained. Normal Asset insert validation and permissions apply; Assets and any generated depreciation schedules remain draft, with no Asset submission or depreciation journal posting by this hook.
- A Frappe v16 Purchase Invoice mixin suppresses only native auto-asset creation when this feature is enabled, including Items whose native auto-create flag is on. Receipt-linked or native invoice Assets already present block creation for review; they are never converted, removed or duplicated silently. The source invoice is locked and each line/unit has a unique deterministic key so repeating the submit hook cannot duplicate drafts.
- ERPNext rejects its standard `purchase_invoice` field on Existing Assets. Dedicated read-only source invoice, line and unit fields preserve provenance without bypassing that validation. The report recognizes those references and apportions direct invoice-line coverage by Asset quantity rather than crediting the entire invoice-line amount to each Asset. **View → Generated Existing Assets** on the invoice opens the corresponding list without replacing native Connections or reinstating capitalization-reconciliation buttons.

This automates preparation of the existing fiscal-year workaround; it does not introduce a separate depreciation engine. Finance still reviews and submits the Assets and subsequent depreciation under the normal ERPNext process.

## Cancellation and reviewed Asset deletion

Cancelling a source Purchase Invoice attempts to cancel and delete its generated Assets and their owned links, even if the creation setting has since been disabled. The web form first explains the number of Assets affected. Server checks apply equally to API-driven cancellation. All Assets are checked before cleanup starts; a failure in cleanup or later invoice cancellation aborts the request and rolls back the transaction. No separate commits or background deletions are used.

On an Asset, **Actions → Cancel and Delete Asset** first shows a preview. The user must confirm cancellation and deletion of the listed records. Submitted records are cancelled before deletion, and already-cancelled links are included. Scope is limited to the Asset, its own depreciation schedules, movements containing only that Asset, Asset Activity records, and depreciation Journal Entries whose account references all identify only that Asset. The user's read, cancel and delete permissions are checked on every affected document. A token tied to the user and current document/ledger snapshots prevents using a stale preview.

Shared journals, shared movements, other Assets, reconciliations, repairs, source purchase documents and other unrelated incoming links block cleanup and must be resolved separately. Acquisition invoices and receipts are never recursively cancelled or deleted by the Asset button. Depreciation journals that also support another Asset's schedule are blockers even if their own account references appear Asset-specific. ERPNext cancellation hooks update depreciation references and ledger reversals; schedules are reloaded and cancelled without attempting to cancel the same journal twice.

Ledger deletion follows **Accounts Settings → Delete Linked Ledger Entries** and the normal transaction deletion hooks. If ledger links exist and the site retains those entries, the preview blocks cleanup rather than bypassing that policy. The feature never changes this setting or directly deletes GL entries. Normal framework link checks, accounting freeze rules, workflows, recovery records and deletion audit behavior remain in effect. Activity created by cancellation is cleaned up before the Asset is deleted; ERPNext's final deletion audit activity is retained as usual.

Staging acceptance checks for this addition:

1. Enable the setting with Finance-approved defaults. Submit an invoice midyear with two fixed-asset lines (including quantity greater than 1), a normal expense line, and company-currency valuation charges. Check draft counts, line/unit source keys, total costs, accounting dimensions, fiscal dates and finance-book values.
2. Repeat with a non-calendar fiscal year, non-depreciable category and native Item auto-create enabled. Check invalid/fractional quantities, UOM conversion, missing Location, returns, source-receipt Assets, and a user without Asset create permission. Replay the hook to confirm no duplicates.
3. Cancel an invoice whose generated Assets are still draft, then test one whose Assets have been submitted and depreciated. Verify permissions and Accounts Settings allow cleanup. Check schedules, Asset-only depreciation JEs, movements, linked ledger behavior and invoice cancellation together. Disable the feature before cancellation and verify cleanup still runs.
4. Use the special Asset button on draft, submitted and cancelled Assets. Check the confirmation, stale preview, draft/cancelled journals, shared JE/movement, reconciliation link, denied delete permission, frozen accounting period and retained-ledger blockers. Trigger a late failure and verify the complete transaction rolls back.
5. After invoice amendment, confirm new line/unit keys create fresh drafts. Verify old Assets must be cleaned up before the original invoice can be cancelled.

## Validation

Isolated unit suite (no site needed):

```sh
python -m unittest av_tools.asset_reconciliation.test_reconciliation av_tools.asset_reconciliation.test_asset_lifecycle -v
```

Frappe integration checks on a disposable migrated ERPNext v16 site:

```sh
bench --site <test-site> run-tests --app av_tools --module av_tools.asset_reconciliation.test_integration
```

Unit tests exercise the app calculations and boundaries with Frappe doubles. They do not replace database migration, native dashboard click-through, or multi-user permission checks on a real bench.

## Backport considerations

Target is `version-16-hotfix`. Do not automatically label for backport before staging validation. For a v15 backport, verify availability/semantics of `frappe.read_only`, permission query arguments, child table dashboard list/count routing, `get_permitted_fieldnames`, and the installed Asset Depreciation Schedule schema. The new Purchase Invoice mixin relies on Frappe v16 `extend_doctype_class`; v15 needs an explicitly composed controller adaptation. Verify Existing Asset fields and schedule cancellation flags on that version too. Carry the source-field migration, pre/post adoption patches and install hook together; retain the typed source Link fields. The repository's `backport-to-<branch>` workflow may be used only after adapting and validating those framework differences. No change to ERPNext core dashboards is required.

The existing live report heuristics remain: depreciation accounts are identified by account-name text; multiple finance books/shared depreciation journals require accounting review. This packaging does not change those financial rules or create GL corrections.
