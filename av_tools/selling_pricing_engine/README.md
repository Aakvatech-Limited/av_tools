# Selling Pricing Engine — Phase 1

An optional **Selling Pricing Engine** module for `version-16-hotfix` only. It creates reviewed selling prices with company settings, Item/warehouse/list rules, fixed overrides and generation fallback. It publishes standard ERPNext **Item Price** records or company-scoped **Location Selling Price** records. It does not create purchase-event automation in this phase.

## Install and activate

1. Deploy this branch to an ERPNext/Frappe v16 test bench and run `bench --site <test-site> migrate` and `bench build --app av_tools`. Restart the bench processes normally.
2. Open **AV Tools → Selling Pricing Engine**. The module ships its own Workspace, Sidebar and Dock entry. Existing customized Dock layouts may need the module enabled manually. No customer navigation arrangements are reset.
3. Create **Selling Price Settings**, select the Company and configure the method/value, minimum gross margin and ordinary rounding. The feature starts **disabled**. The only Phase 1 mode is **Manual**.
4. Check **Stock Settings → Auto insert Price List rate if missing**. It must be off before enabling this engine, because ERPNext's transaction-driven Item Price writes would bypass revision review. The engine refuses activation/calculation/sales repricing while that conflicting setting is on; it does not change the global setting itself. Review any other app's purchase-to-price hooks before activation. This branch contains no automatic purchase-based selling-price updater to disable.
5. Enable the Company settings and create an enabled **Selling Price List Policy** for each managed list. An optional generation fallback list must be enabled, selling and use the same currency.
6. Map each business HQ/Branch to an existing leaf Warehouse in that Company. Phase 1 uses this mapping, not a new Branch master. Independent Branch override tiers are Phase 2.

**Standard Item Price is global to its Price List.** A managed list can belong to only one pricing Company. Use separate lists where companies require independent standard prices; a company checkbox cannot make a shared native Item Price company-specific.

## Permissions

| Operation | Default permission |
|---|---|
| Company settings / activation | System Manager |
| Policies, rules, calculate, review, submit/publish, reports | System Manager or Sales Manager |
| Cost retrieval | Also requires native Purchase Invoice read permission and access to the selected source invoice |
| Standard price writes | Also requires native Item Price create/write permissions |
| Read published location prices | Sales User, Sales Manager, System Manager |
| Read supplier/cost fields on location prices | Sales Manager or System Manager, permission level 1 |
| Preserve a manually entered sales rate | Explicit document checkbox plus the role configured in Company settings |

Frappe Company, Item, Price List and Warehouse permissions are checked before processing a context. Purchase costs come from permission-filtered submitted invoices, not unrestricted supplier cost queries. Sales endpoints return rates and price-source references, never procurement costs.

## Generate, review and publish

1. Create and save a **Selling Price Revision** with Company, Price List, effective-from date, optional effective-to date and Warehouse. A blank Warehouse generates standard Item Prices. Optionally select an Item or selling UOM; otherwise each Item's sales UOM / stock UOM is used.
2. Click **Calculate / Recalculate**. This creates a server-owned preview; it does not update prices. Inspect cost/source invoice, supplier, rule, previous effective price, calculated/rounded/proposed prices, margin and exception reason.
3. Select the rows to publish. Resolve or deselect **Blocked** rows. Known margins below the configured minimum cannot be overridden in Phase 1.
4. Fixed or fallback prices with no usable cost show **Requires Review**. Publication requires an explicit **Acknowledge Unverified Margin** checkbox and a meaningful review note on each such row. Unknown margin is not treated as verified 0% margin. Users still need cost-read authorization to perform the review.
5. **Submit** the revision. Submission rechecks all selected rows against current configuration, rules, purchase evidence, exchange rates and existing prices before the first write. A changed preview must be recalculated. Price writes, fixed-rule protection and revision history share the normal document-submit database transaction.

Published revisions cannot be cancelled or deleted. Publish a correcting revision. Deselecting every row cannot publish an empty revision. Repeated submission/publication does not create duplicate same-context price records. Ordinary edits cannot replace preview rates, snapshots or publication stamps; only selection and review fields are editable.

Changing revision filters invalidates the previous preview and imported input. Save the filters, then calculate/import again. A configurable per-revision limit (default 500, maximum 5,000 rows) prevents unbounded foreground processing; exceeding it raises an explicit error rather than silently omitting items.

## Calculation and fallback

| Method | Formula | Cost 1,000; value 20 |
|---|---|---:|
| Markup Percentage | Cost × (1 + percentage / 100) | 1,200 |
| Target Gross Margin | Cost ÷ (1 − percentage / 100) | 1,250 |
| Fixed Addition | Cost + amount | 1,020 |
| Fixed Selling Price | Explicit rate | 20 |

Target margin must be below 100%. Negative/nonfinite values and non-positive fixed selling prices are rejected. **Use Default** is distinct from **Override with 0**. Fixed rates are final prices and are not changed by global commercial rounding. Storage precision still applies, and imports exceeding configured precision are rejected.

The Phase 1 calculation hierarchy is Item + Warehouse + Price List, Item + Price List, Warehouse + Price List, list policy, then Company default. An exact UOM wins over a wildcard UOM within the same specificity tier. Equally specific overlapping rules are rejected. Supplier and Item Group conditions are deferred to Phase 2.

Costs use the latest **permitted, submitted, non-return Purchase Invoice** for that Item and Company, at or before the effective date. This is a company-wide net invoice cost, not warehouse valuation or landed cost. Latest is ordered by posting date, creation and name; where the same Item appears more than once in that invoice, the last eligible line is used. Cost is `base_net_amount / stock_qty`, converted to selling UOM and Price List currency. Missing UOM factors are errors. Foreign currencies require a stored, dated **Currency Exchange** record (direct or inverse); there is no silent rate of 1 or external FX lookup during publication.

When a cost-based rule/default cannot obtain usable cost, generation tries the configured Base Price List's valid general Item Price, then the target list's valid standard Item Price for a location. If neither exists, the row is blocked. No other location's price, lowest sample price or zero is used as a default. Fallback lists are same-currency and cycle checked. Alternative cost-source chains and cross-list runtime resolution are later phases.

No Rounding, Nearest (half-up), Round Up and Round Down support positive configurable increments such as 1, 10, 50, 100, 500 and 1,000. Margin is checked after commercial and storage rounding. The default **Retain Price Decreases** setting keeps an existing effective selling rate when a cost-based proposal would reduce it; explicit fixed overrides still take precedence.

## Import fixed prices

Use **Import Fixed Prices** on a saved revision. Paste long-form CSV with exactly these headers. Dates come from the revision.

```csv
item_code,warehouse,rate,uom,currency,tax_basis
VERIFIED-ITEM-CODE,Mbagala Warehouse - TF,1725,Nos,TZS,Tax Exclusive
VERIFIED-ITEM-CODE,Arusha Warehouse - TF,,Nos,TZS,Tax Exclusive
VERIFIED-ITEM-CODE,,1700,Nos,TZS,Tax Exclusive
```

These are illustrative identifiers; use verified site Item Codes and Warehouse names. A blank rate requests fallback. A blank Warehouse means a standard Item Price, even when a Warehouse is selected on the revision header. Zero rates, duplicate Item/Warehouse/UOM combinations, unknown mappings, wrong currency, inclusive tax basis and malformed CSV are rejected. The original sample workbook must still be reconciled before a client import; its prices, currency, UOM and tax basis are not assumed.

Import only creates a preview. On publication, fixed rows create/update an Item/UOM/location-specific fixed rule, so later cost changes do not overwrite them. Publishing a later fixed-price period closes the preceding matching rule/price period. Future overlapping prices require explicit end dates or correction before publication. An authorized manager can amend/disable a fixed rule and publish a reviewed replacement; submitted revisions retain the original calculation evidence.

## Sales behavior

The existing av_tools Item Details override is extended, preserving its quantity option. Frappe v16 mixins also enforce resolution in the native server-side item-details path used by saves, API-created documents and server-reactive forms. Client code refreshes the display when Warehouse, UOM, price list, date or currency changes and discards stale responses.

| Precedence | Behavior |
|---|---|
| Locked mapped source rate | Preserve ERPNext's maintain-same-rate source behavior |
| Customer-specific Item Price / blanket agreement / batch pricing / free item | Preserve native pricing |
| Applied ERPNext Pricing Rule | Preserve its result |
| Explicit authorized manual-rate checkbox | Preserve entered rates |
| Valid published Warehouse price | Use location price within selected list, Company, UOM and effective period |
| No Warehouse override | Use ERPNext's native standard Item Price resolution |
| No published price | Show a missing-price exception; do not calculate or publish during sales |

Quotation, Sales Order and non-POS Sales Invoice are included. Returns, Delivery Note and POS are left to native behavior in Phase 1. Percentage/fixed discounts and ordinary manual margins continue after the engine baseline where no higher-priority Pricing Rule applies. Header discounts/taxes remain ERPNext calculations. Minimum-margin publication protection is not a guarantee of realized sales margin after discounts, returns and actual COGS.

## Reports and navigation coverage

| Target | Where to find it | Scope |
|---|---|---|
| Selling Price Revision | Transactions | Calculate, import, review, publish and audit |
| Selling Price List Policy; Selling Price Rule | Pricing Policies | List and Item/location policies |
| Location Selling Price | Pricing Policies | Read-only published overrides; cost fields restricted |
| Selling Price Revision Item | Internal child only | Never a standalone navigation target |
| Selling Price Settings | Settings | Company activation/defaults; permission restricted |
| Selling Price and Margin Review | Reports | Published rate, comparable cost, gross profit/unit and current/proposed margins |
| Missing Selling Prices | Reports | Missing effective published prices; proposed generation result shown separately |
| Below Minimum Selling Margin | Reports | Current/proposed price margin exceptions |
| Location Selling Price Matrix | Reports | Items × permitted Company warehouses, with override/standard-fallback/missing indicators |
| Selling Price Revision History | Reports | Previous/new rates, source, invoice/rule, publisher and review note |

All reports require Company and Price List and support applicable Item, Warehouse, UOM and effective-as-on filters. The matrix is limited to 25 permitted warehouses at once; select a Warehouse on larger sites. Reports never sum mixed currencies. Full dashboards, supplier trends and realized-margin reporting remain Phase 4.

## Validation and RTM handoff

The baseline is the existing four-phase RTM, **MVP-01 through MVP-14**. The table above covers operating reports and discoverability. The implementation is split across `calculation.py` (arithmetic/precedence), `repository.py` (permitted sources), `engine.py` (preview and fingerprints), `revision.py` / `publication.py` (controls and audit), `sales.py` (server integration) and the six DocType controllers/JSON definitions.

Run isolated tests without a bench:

```bash
python -m unittest av_tools.selling_pricing_engine.test_pricing -v
```

After migrating an ERPNext v16 **test site** with the `_Test Company` fixture:

```bash
bench --site <test-site> run-tests --module av_tools.selling_pricing_engine.test_integration
```

The bench tests exercise real preview storage/browser serialization, standard/location publication, repeat submission, fixed imports, stale-cost rejection and tamper protection. They deliberately replace only the cost retriever; separately validate real Purchase Invoice retrieval and sales flows in UAT.

Release checks still required on the test site: migration and native navigation import; real cost and FX/UOM evidence; ordinary-user permission behavior; sales Pricing Rule/customer/manual/source precedence; all five reports; mixed Warehouse sales rows; original sample import; and rollback on failed multi-row publication. Do not mark an RTM item UAT Passed from the isolated test suite alone.

Phases 2–4 remain as planned: supplier/Item Group/full Branch policies and additional cost bases; purchase-event/approval automation; advanced costing/psychological rounding, remaining channels, complete analytics and final client acceptance. This change adds no scheduled jobs and does not modify historical sales, accounting or stock valuation.
