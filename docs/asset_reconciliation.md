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

## Validation

Isolated unit suite (no site needed):

```sh
python -m unittest av_tools.asset_reconciliation.test_reconciliation -v
```

Frappe integration checks on a disposable migrated ERPNext v16 site:

```sh
bench --site <test-site> run-tests --app av_tools --module av_tools.asset_reconciliation.test_integration
```

Unit tests exercise the app calculations and boundaries with Frappe doubles. They do not replace database migration, native dashboard click-through, or multi-user permission checks on a real bench.

## Backport considerations

Target is `version-16-hotfix`. Do not automatically label for backport before staging validation. For a v15 backport, verify availability/semantics of `frappe.read_only`, permission query arguments, child table dashboard list/count routing, `get_permitted_fieldnames`, and the installed Asset Depreciation Schedule schema. Carry both pre/post patches and the install hook together; retain the typed source Link fields. The repository's `backport-to-<branch>` workflow may be used only after adapting and validating those framework differences. No change to ERPNext core dashboards is required.

The existing live report heuristics remain: depreciation accounts are identified by account-name text; multiple finance books/shared depreciation journals require accounting review. This packaging does not change those financial rules or create GL corrections.
