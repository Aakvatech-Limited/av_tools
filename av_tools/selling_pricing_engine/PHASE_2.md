# Phase 2 — Pricing Policies and Sales Manager Dashboard

This release implements the Pricing Policies phase in the separate Selling Pricing Engine module on `version-16-hotfix`. It includes the operational dashboard for both Phase 1 and Phase 2. It does not mark client UAT or outstanding requirements decisions accepted.

## Activation and migration

1. Deploy the combined branch, run `bench --site <test-site> migrate`, build av_tools and restart normal bench processes. The existing custom-field migration installs the Warehouse mapping and sales provenance fields. The dashboard sync creates missing standard cards/charts/dashboard without replacing site-specific edits.
2. In each Company’s Selling Price Settings, leave the existing engine activation and Stock Settings conflict safeguards in place. Enable **Expanded Pricing Policies** to activate Phase 2; the default is off, preserving Phase 1 behavior after migration.
3. Reuse ERPNext **Branch**. Set **Pricing Branch** on each participating Warehouse. The Warehouse Company scopes the mapping; the same Branch name can be mapped in separate companies without sharing prices. At least one enabled Warehouse in the selected Company must map a Branch before a Branch-only policy/price can be used. Grant appropriate Branch read/select permissions to pricing managers and participating sales users through native Role Permission Manager. This release does not grant new master-data permissions automatically.
4. Create Supplier and/or Item Group rules as needed. **Include Child Item Groups** is explicit and defaults off. Enable **Allow Alternate List During Sales** only on policies requiring runtime fallback, and select their same-currency fallback list.
5. Recalculate open revisions after changing settings, mappings, rules or source evidence. Publication still rechecks the fingerprint before any price writes. Submitted historical revisions remain immutable.

## Rule precedence and inheritance

All tiers are scoped to Company and Price List. Highest first:

| Priority | Rule scope |
|---:|---|
| 100 | Item + Warehouse + Supplier |
| 90 | Item + Warehouse |
| 85 | Item + Branch + Supplier |
| 80 | Item + Branch |
| 70 | Item + Supplier |
| 60 | Item |
| 50 | Item Group + Warehouse |
| 45 | Item Group + Branch |
| 40 | Item Group |
| 35 | Supplier + Warehouse |
| 33 | Supplier + Branch |
| 30 | Supplier |
| 20 | Warehouse |
| 10 | Branch |
| 0 | Unscoped rule, then Price List policy and Company default |

Within an Item Group tier, the closest matching group wins; ancestor groups apply only with explicit inheritance. Exact UOM wins within the same scope/group tier. Equal ranks are rejected rather than chosen by record order. Item and Item Group cannot both be set on one rule, nor can Warehouse and independent Branch. Supplier can restrict Item rules and Supplier-only location rules; Supplier + Item Group rules are deliberately rejected because no precedence for that combination was specified.

Each setting inherits independently. **Use Default** on a more specific rule inherits the next applicable rule, then the list policy, then Company settings. **Override** with 0 explicitly means zero markup/addition; it does not bypass minimum-margin protection. Rules remain maintainable through standard lists, Data Import and Data Export rather than a duplicate policy master.

These Branch insertions and the Item Group-only tier make the roadmap’s formerly open positions explicit. They are implementation defaults for review, not a claim of client sign-off.

## Supplier selection and cost evidence

An explicit **Cost Supplier** constrains procurement evidence and supplier rules. Otherwise the supplier on the selected permitted procurement evidence determines the supplier-specific policy. A supplier policy changing cost basis retains that supplier constraint during the second cost read. If the source is valuation and no Supplier was selected, there is no inferred supplier rule.

| Cost basis | Definition |
|---|---|
| Latest Submitted Purchase Invoice | Latest permitted submitted non-return PI; last eligible matching line. Phase 1 default. |
| Current Purchase Invoice | Explicitly selected submitted PI, in the pricing Company and not later than the effective date. |
| Current Purchase Receipt | Explicitly selected submitted PR with the same checks. |
| Latest Submitted Purchase Receipt | Latest permitted submitted non-return PR; last eligible matching line. |
| Latest Purchase Rate | Latest eligible permitted submitted PI or PR by posting date, creation and document name. This reads both source types and requires their read permissions. |
| Supplier Latest Purchase Rate | Latest eligible permitted submitted PI restricted to an explicitly selected Supplier. |
| Valuation Rate / Warehouse Valuation Rate | Latest permitted, non-cancelled Stock Ledger Entry through the selected day, for the explicit Warehouse and Company. Both names use this warehouse-scoped historical ledger evidence; no global Item valuation or arbitrary warehouse is assumed. |

Procurement cost is `base_net_amount / stock_qty`, normalized to selling UOM and target Price List currency through stored dated exchange rates. It excludes additional landed charges; select ledger valuation when booked stock cost is required. Ledger valuation is read only and can include booked landed-cost/reposting effects. Non-positive or unavailable evidence produces an exception; an older positive valuation is not substituted for a latest non-positive one.

Optional **Cost Source Fallbacks** lists an ordered chain, one supported source name per line. There is no implicit switch from invoice cost to valuation. Permissions failures stop processing; they are not a reason to fall back to a more accessible source. Source type/document/row, supplier, UOM/FX normalization and attempted source chain are retained in calculation evidence. Changing selected source evidence changes the publication fingerprint.

## Branch prices and sales fallback

A revision with Branch but no Warehouse publishes Branch-scoped **Location Selling Price** records. A Warehouse revision publishes Warehouse records, with mapped Branch retained as provenance. Company remains part of all location price contexts. Explicit Branch conflicting with the selected Warehouse is rejected.

After native agreements/Pricing Rules/manual-rate preservation, lookup is:

1. Effective Warehouse price, when a Warehouse is present.
2. Effective mapped or explicitly selected Branch price.
3. Effective general standard Item Price, including the existing stock-UOM normalization.
4. Only when enabled on the policy, repeat the location/standard lookup in the configured same-currency alternate list. Cycles, conflicting prices, disabled lists and lists managed by another Company are errors.

Sales rows retain **Resolved Pricing List**, **Pricing Resolution** and the location source link where applicable. The transaction’s selected selling list is not changed. No costs are returned to sales endpoints; discounts and margins still apply after the resolved baseline, preserving the Phase 1 integration order. Generation fallback remains distinct from runtime lookup.

The Phase 1 fixed CSV contract is unchanged: blank Warehouse means standard price. Branch revisions use Branch-scoped fixed rules and Calculate; fixed CSV import on a Branch revision is rejected rather than interpreting blank Warehouse as Branch.

## Filters and reports

Revision, operational reports and dashboard filters add Branch, Cost Supplier, Item Group, optional descendants and Brand. Current-document cost sources additionally require Source Type and Source Document. Cost Supplier constrains the cost used for each eligible Item; Items lacking that supplier’s evidence remain visible as fallback/review/blocked outcomes rather than being silently omitted.

| Report | Purpose |
|---|---|
| Supplier Cost Comparison | Latest comparable permitted PI or PR cost per Item/Supplier, with UOM, currency and source links. No pooled supplier average. |
| Selling Margin by Location | Live proposed and published margins across permitted mapped warehouses; at most 25 locations. |
| Selling Margin by Price List | Same live calculation per managed list in one Company. Select one Price List per view; unbounded all-list comparisons are disabled. Currency stays on each row; no mixed-currency total. |
| Selling Price Fallback Usage | Submitted revision evidence showing generated Base/Standard fallback and its originating fallback list. This is saved generation history, not a log of every sales runtime lookup. |

The existing five pricing reports are retained. Their proposal path uses the expanded rule/cost logic when enabled; the manager overview is the sixth base report, and these four expand the module to ten reports.

## Combined dashboard

**Sales Manager Pricing** is available in the module sidebar and embedded on its workspace. It has **16 cards and six charts**. Its filters are Company, Price List, Warehouse, Branch, Item, Item Group/descendants, Brand, Cost Supplier and effective date, as applicable to the measure. Explicit current cost-source filters belong to calculation reports; opening the dashboard never computes new purchase costs.

| Card group | Measures |
|---|---|
| Coverage | Active Sellable Items; Items With Effective Selling Prices; Missing Selling Prices; Invalid or Overlapping Selling Prices |
| Workload | Draft Price Revisions; Price Revisions Awaiting Publication; Blocked Pricing Rows; Pricing Rows Requiring Review |
| Margin and fallback evidence | Pricing Rows Below Minimum Margin; Fallback Pricing Rows |
| Location and policy coverage | Active Location Selling Prices; Active Branch Selling Prices; Active Supplier Pricing Rules; Active Item Group Pricing Rules |
| Lifecycle | Location Prices Expiring in 30 Days; Price Revisions Published This Month |

Published pipeline/fallback/cost-source measures use the last six calendar months, while all outstanding drafts remain included.

Charts: effective coverage (standard/Warehouse/Branch/alternate/missing/invalid), revision pipeline, blocked/pending review exceptions, six-month publication trend, supplier/Item Group rule coverage, and saved cost-source mix.

Margin exceptions are saved calculated-revision rows, not a live calculation of today’s purchase cost. Fallback and cost-source charts count saved revision rows, not unique Items or realized sales. Deselected exception rows remain part of workload; a valid acknowledgement plus a review note of at least 10 characters removes an unverified margin from pending review. Active location prices count enabled effective records, including Branch records; the Branch card is a subset. Rule counts are effective rule records, not a claim that every eligible Item has a matching rule. Supplier filters affect source-backed revision evidence and supplier rules, not the public selling-price coverage denominator.

Use **Selling Pricing Manager Overview** for one filter set across measures. Select Company, Price List and Item Group in the overview and click **Use Scope for Dashboard** to save a private scope for all cards/charts. Explicit widget filters take precedence. **Reset Dashboard Scope** clears that preference. The saved scope does not freeze the effective date. Multi-policy sites must select their Price List explicitly. Standard imports do not override an existing customized dashboard. Dashboard coverage supports **5,000 SKUs per Price List / Item Group**, independently of the revision batch limit. Catalogues above 500 Items require Item Group or a single Item selection. Both phase paths batch standard, Warehouse, Branch and configured alternate-list prices; historical price records do not consume the SKU count. No per-SKU price queries or purchase-cost calculations run for coverage. Live cost/margin reports have explicit **Page / Items per Page**, with at most 500 Items per request (also bounded by Max Revision Items). Their message states the full eligible scope and that exception filtering applies to the selected page. Large location comparisons/matrices require one Warehouse. History has explicit date and record pages, and excludes audit snapshots from reads. Large historical scans fail above 100,000 scoped records rather than displaying partial totals.

## Validation and remaining phases

Isolated tests cover the original pricing behavior, expanded precedence/inheritance, supplier evidence, cost normalization and fallback, ledger cutoff and cancellation guards, permission failures, Branch/alternate-list lookup, cycle/currency guards, dashboard counts and asset installation/idempotency. CI runs all three isolated modules.

Bench tests include Branch price publication/resolution and Item Group filter/browser round-trip/publication, in addition to the existing Phase 1 persistence cases. They require a migrated v16 test site; source retrieval is mocked in those lifecycle tests, so actual PI/PR/SLE evidence and permission combinations must also be validated in UAT.

Still required before deployment acceptance: run migration/build, real-source and FX/UOM tests, user/Company/Branch permission tests, native sales precedence, all ten reports, dashboard rendering/filter/drill-through checks and rollback tests. No client UAT status is marked passed from isolated tests. Reconcile the original sample workbook and obtain review of the open decision defaults above.

Phase 3 retains purchasing-event automation, approval thresholds/queues and cancellation/retry handling. Phase 4 retains moving/weighted purchase cost, psychological rounding, remaining sales channels, supplier trends/realized-margin analytics and final RTM/UAT closure. The operational dashboard has moved into Phase 2 by user instruction; later analytics are still separate.

## 5,000-SKU scale checks

The isolated scale suite creates 5,000 eligible SKUs and 10,000 price records (one expired and one current per SKU). It verifies all 5,000 effective prices are counted using at most 30 paged Item Price reads and no per-SKU Document reads. It also verifies ten 500-Item detail pages cover the complete catalogue without duplicate/omitted Items, explicit Item Group scoping, private saved dashboard scope, unknown-margin handling, history paging without snapshots, and that missing-price reports skip costing already-priced Items. These are deterministic read-budget tests, not a production database timing benchmark.
