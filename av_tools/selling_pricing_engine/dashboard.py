"""Permission-scoped pricing workload and published-price coverage, without costing."""

from collections import Counter, defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, getdate, today

from av_tools.selling_pricing_engine import repository
from av_tools.selling_pricing_engine.access import (
	LOCATION,
	POLICY,
	REVISION,
	RULE,
	check_context,
	manager,
	settings,
)
from av_tools.selling_pricing_engine.coverage import PublishedCoverage
from av_tools.selling_pricing_engine.policies import check_filters, item_filters
from av_tools.selling_pricing_engine.report_scope import catalog, chunks, permitted_names, read_rows

MAX_ROWS = 5000
METRICS = {
	"active_items": "Active Sellable Items",
	"priced_items": "Items With Effective Selling Prices",
	"invalid_prices": "Invalid or Overlapping Selling Prices",
	"below_margin": "Pricing Rows Below Minimum Margin",
	"fallback_rows": "Fallback Pricing Rows",
	"branch_prices": "Active Branch Selling Prices",
	"supplier_rules": "Active Supplier Pricing Rules",
	"group_rules": "Active Item Group Pricing Rules",
	"missing_prices": "Missing Selling Prices",
	"draft_revisions": "Draft Price Revisions",
	"calculated_revisions": "Price Revisions Awaiting Publication",
	"blocked_rows": "Blocked Pricing Rows",
	"review_rows": "Pricing Rows Requiring Review",
	"active_locations": "Active Location Selling Prices",
	"expiring_locations": "Location Prices Expiring in 30 Days",
	"published_month": "Price Revisions Published This Month",
}
VIEWS = (
	"Coverage",
	"Revision Pipeline",
	"Review Exceptions",
	"Publication Trend",
	"Policy Coverage",
	"Cost Sources",
)


def bounded(doctype, **kwargs):
	rows = frappe.get_list(doctype, limit_page_length=MAX_ROWS + 1, **kwargs)
	if len(rows) > MAX_ROWS:
		frappe.throw(
			_("Dashboard exceeds 5,000 records. Narrow the Company, Price List, Item or Warehouse filters.")
		)
	return rows


SCOPE_KEY = "selling_pricing_dashboard_scope"
SCOPE_FIELDS = (
	"company",
	"price_list",
	"item_group",
	"include_child_groups",
	"warehouse",
	"branch",
	"brand",
	"supplier",
)


def context(filters, *, use_defaults=True):
	filters = frappe._dict(filters or {})
	if not {"Sales Manager", "System Manager"}.intersection(frappe.get_roles()):
		frappe.throw(_("Sales Manager or System Manager access is required."), frappe.PermissionError)
	frappe.has_permission(REVISION, "read", throw=True)
	if use_defaults:
		try:
			saved = frappe.parse_json(frappe.defaults.get_user_default(SCOPE_KEY)) or {}
		except (ValueError, TypeError):
			saved = {}
		if isinstance(saved, dict) and all(
			not filters.get(key) or filters.get(key) == saved.get(key) for key in ("company", "price_list")
		):
			for key in SCOPE_FIELDS:
				if (
					not filters.get(key)
					and saved.get(key) is not None
					and not (key == "include_child_groups" and key in filters)
				):
					filters[key] = saved[key]
	filters.company = filters.company or frappe.defaults.get_user_default("Company")
	# Never choose an arbitrary company or managed list on a multi-company site.
	criteria = {"enabled": 1}
	for key in ("company", "price_list"):
		if filters.get(key):
			criteria[key] = filters[key]
	policies = frappe.get_list(
		POLICY, filters=criteria, fields=["company", "price_list"], limit_page_length=2
	)
	if len(policies) != 1:
		frappe.throw(
			_(
				"Select a Company and Price List with one enabled pricing policy in the widget filters or Selling Pricing Manager Overview report."
			)
		)
	filters.company, filters.price_list = policies[0].company, policies[0].price_list
	manager(filters.company)
	check_context(filters.company, filters.price_list, filters.warehouse, filters.item_code)
	check_filters(filters)
	config = settings(filters.company)
	if not config.get("enable_phase_2") and any(
		filters.get(key) for key in ("branch", "supplier", "source_document")
	):
		frappe.throw(_("Enable Expanded Pricing Policies before using Phase 2 filters."))
	filters.as_on = str(getdate(filters.as_on or today()))
	if filters.get("metric") and filters.metric not in METRICS:
		frappe.throw(_("Unknown pricing dashboard metric."))
	if filters.get("chart_view") and filters.chart_view not in VIEWS:
		frappe.throw(_("Unknown pricing dashboard chart."))
	catalog(filters)
	return filters, config


def summarize_revisions(revisions, filters):
	"""Count saved review evidence; unchecked rows still remain visible as workload."""
	counts = Counter()
	pipeline = Counter()
	as_on = getdate(filters.as_on)
	months = [str(add_months(as_on.replace(day=1), offset))[:7] for offset in range(-5, 1)]
	trend = dict.fromkeys(months, 0)
	for doc, rows in revisions:
		for row in rows:
			counts["fallback_rows"] += "Fallback" in (row.get("price_source") or "")
			counts["source:" + (row.get("cost_source") or "No usable cost")] += 1
			if (
				doc.docstatus == 0
				and doc.status == "Calculated"
				and row.get("cost_available")
				and row.get("proposed_margin") is not None
			):
				counts["below_margin"] += row.proposed_margin < (row.get("minimum_margin") or 0)
		if doc.docstatus == 0:
			pipeline[doc.status] += 1
			if doc.status == "Draft":
				counts["draft_revisions"] += 1
			if doc.status == "Calculated":
				counts["calculated_revisions"] += 1
				counts["blocked_rows"] += sum(row.result == "Blocked" for row in rows)
				counts["review_rows"] += sum(
					row.result == "Requires Review"
					and not (row.acknowledge_unknown_margin and len((row.review_note or "").strip()) >= 10)
					for row in rows
				)
		elif doc.docstatus == 1 and doc.status == "Published":
			pipeline["Published"] += 1
			if doc.published_on and getdate(doc.published_on) <= as_on:
				month = str(doc.published_on)[:7]
				if month in trend:
					trend[month] += 1
				if month == str(as_on)[:7]:
					counts["published_month"] += 1
	return counts, pipeline, trend


def revision_stats(filters):
	criteria = {
		"company": filters.company,
		"price_list": filters.price_list,
		"docstatus": ["<", 2],
		"creation": ["<", add_days(filters.as_on, 1)],
	}
	window = add_months(getdate(filters.as_on).replace(day=1), -5)
	parents = read_rows(
		REVISION,
		filters=criteria,
		fields=[
			"name",
			"status",
			"docstatus",
			"published_on",
			"item_code",
			"warehouse",
			"branch",
			"supplier",
		],
		or_filters=[[REVISION, "docstatus", "=", 0], [REVISION, "published_on", ">=", window]],
	)
	parents = [
		doc
		for doc in parents
		if doc.docstatus == 0 or (doc.published_on and getdate(doc.published_on) <= getdate(filters.as_on))
	]
	by_parent, has_children = defaultdict(list), set()
	criteria_items = None
	if filters.get("item_group") or filters.get("brand") or filters.get("item_code"):
		criteria_items = {item.name for item in catalog(filters)}
	for batch in chunks([doc.name for doc in parents]):
		# The parent IDs came from get_list with Company/User Permissions. Child
		# reads cannot reach another parent's data and exclude large audit snapshots.
		base = {"parent": ["in", batch], "parenttype": REVISION, "parentfield": "items"}
		has_children.update(
			frappe.get_all(
				"Selling Price Revision Item",
				filters=base,
				pluck="parent",
				group_by="parent",
				limit_page_length=0,
			)
		)
		criteria = dict(base)
		if criteria_items is not None:
			criteria["item_code"] = ["in", sorted(criteria_items)]
		for key in ("warehouse", "branch", "supplier"):
			if filters.get(key):
				criteria[key] = filters[key]
		start = 0
		while True:
			rows = frappe.get_all(
				"Selling Price Revision Item",
				filters=criteria,
				fields=[
					"parent",
					"item_code",
					"warehouse",
					"branch",
					"supplier",
					"result",
					"cost_available",
					"proposed_margin",
					"minimum_margin",
					"acknowledge_unknown_margin",
					"review_note",
					"price_source",
					"cost_source",
				],
				order_by="name",
				limit_start=start,
				limit_page_length=500,
			)
			for row in rows:
				by_parent[row.parent].append(row)
			start += len(rows)
			if sum(len(values) for values in by_parent.values()) > 100000:
				frappe.throw(
					_(
						"Revision analytics exceeds 100,000 scoped rows. Narrow the Price List / Item Group or Warehouse."
					)
				)
			if len(rows) < 500:
				break
	all_rows = [row for rows in by_parent.values() for row in rows]
	links = (
		("item_code", "Item"),
		("warehouse", "Warehouse"),
		("branch", "Branch"),
		("supplier", "Supplier"),
	)
	allowed = {
		key: permitted_names(doctype, [row.get(key) for row in all_rows] + [doc.get(key) for doc in parents])
		for key, doctype in links
	}

	def permitted(row):
		return all(not row.get(key) or row.get(key) in allowed[key] for key, _doctype in links)

	revisions = []
	for doc in parents:
		rows = [row for row in by_parent.get(doc.name, []) if permitted(row)]
		if not rows:
			if doc.name in has_children:
				continue
			if not permitted(doc) or (criteria_items is not None and doc.item_code not in criteria_items):
				continue
			if any(
				filters.get(key) and doc.get(key) != filters.get(key)
				for key in ("warehouse", "branch", "supplier")
			):
				continue
		revisions.append((doc, rows))
	return summarize_revisions(revisions, filters)


def effective(row, date):
	return (not row.valid_from or getdate(row.valid_from) <= date) and (
		not row.valid_upto or getdate(row.valid_upto) >= date
	)


def location_rows(filters):
	frappe.has_permission(LOCATION, "read", throw=True)
	criteria = {"company": filters.company, "price_list": filters.price_list, "enabled": 1}
	for key in ("item_code", "warehouse", "branch"):
		if filters.get(key):
			criteria[key] = filters[key]
	if filters.get("item_group") or filters.get("brand"):
		criteria["item_code"] = ["in", [item.name for item in catalog(filters)]]
	rows = read_rows(
		LOCATION,
		filters=criteria,
		fields=[
			"name",
			"item_code",
			"warehouse",
			"branch",
			"uom",
			"currency",
			"rate",
			"valid_from",
			"valid_upto",
		],
	)
	links = (("item_code", "Item"), ("warehouse", "Warehouse"), ("branch", "Branch"))
	allowed = {key: permitted_names(doctype, [row.get(key) for row in rows]) for key, doctype in links}
	return [
		row
		for row in rows
		if all(not row.get(key) or row.get(key) in allowed[key] for key, _doctype in links)
		and effective(row, getdate(filters.as_on))
	]


def coverage(filters, config, locations=None, *, items=None):
	return PublishedCoverage(filters, config, items=items).counts()


def overview(filters=None):
	filters, config = context(filters)
	metric, view = filters.get("metric"), filters.get("chart_view") or "Coverage"
	chart_only = filters.get("chart_only") in (1, "1", True)
	counts, pipeline, trend, prices = Counter(), Counter(), {}, Counter()
	need_revisions = (
		metric
		in {
			"draft_revisions",
			"calculated_revisions",
			"blocked_rows",
			"review_rows",
			"published_month",
			"below_margin",
			"fallback_rows",
		}
	) or (not metric and (not chart_only or view not in ("Coverage", "Policy Coverage")))
	need_coverage = metric in {"missing_prices", "active_items", "priced_items", "invalid_prices"} or (
		not metric and (not chart_only or view == "Coverage")
	)
	need_locations = (
		need_coverage
		or metric in {"active_locations", "expiring_locations", "branch_prices"}
		or (not metric and not chart_only)
	)
	need_rules = metric in {"supplier_rules", "group_rules"} or (
		not metric and (not chart_only or view == "Policy Coverage")
	)
	if need_rules:
		counts.update(rule_counts(filters, config))
	if need_revisions:
		revision_counts, pipeline, trend = revision_stats(filters)
		counts.update(revision_counts)
	if need_locations:
		locations = location_rows(filters)
		counts["active_locations"] = len(locations)
		counts["branch_prices"] = sum(not row.warehouse and bool(row.get("branch")) for row in locations)
		counts["expiring_locations"] = sum(
			bool(row.valid_upto) and getdate(row.valid_upto) <= getdate(add_days(filters.as_on, 30))
			for row in locations
		)
	if need_coverage:
		prices = coverage(filters, config, locations)
		counts["missing_prices"] = prices["Missing"]
		counts["active_items"] = sum(prices.values())
		counts["priced_items"] = sum(
			prices[key]
			for key in ("Standard price", "Location override", "Branch override", "Alternate list")
		)
		counts["invalid_prices"] = prices["Invalid / overlapping"]
	keys = [metric] if metric else list(METRICS)
	if chart_only:
		available = set()
		if need_coverage:
			available.update(("active_items", "priced_items", "missing_prices", "invalid_prices"))
		if need_locations:
			available.update(("active_locations", "expiring_locations", "branch_prices"))
		if need_revisions:
			available.update(
				(
					"draft_revisions",
					"calculated_revisions",
					"blocked_rows",
					"review_rows",
					"published_month",
					"below_margin",
					"fallback_rows",
				)
			)
		if need_rules:
			available.update(("supplier_rules", "group_rules"))
		keys = [key for key in keys if key in available]
	columns = [{"fieldname": key, "label": _(METRICS[key]), "fieldtype": "Int", "width": 180} for key in keys]
	row = {key: counts[key] for key in keys}
	columns = [
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company"},
		{"fieldname": "price_list", "label": _("Price List"), "fieldtype": "Link", "options": "Price List"},
		{"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group"},
		*columns,
	]
	row.update(company=filters.company, price_list=filters.price_list, item_group=filters.get("item_group"))
	chart_data = {
		"Coverage": [
			(label, prices[label])
			for label in (
				"Standard price",
				"Location override",
				"Branch override",
				"Alternate list",
				"Missing",
				"Invalid / overlapping",
			)
		],
		"Revision Pipeline": [(label, pipeline[label]) for label in ("Draft", "Calculated", "Published")],
		"Review Exceptions": [
			(_("Blocked Rows"), counts["blocked_rows"]),
			(_("Pending Margin Reviews"), counts["review_rows"]),
		],
		"Publication Trend": list(trend.items()),
		"Policy Coverage": [
			("Supplier rules", counts["supplier_rules"]),
			("Item Group rules", counts["group_rules"]),
		],
		"Cost Sources": [
			(key.removeprefix("source:"), value)
			for key, value in sorted(counts.items())
			if key.startswith("source:")
		],
	}[view]
	chart = {
		"data": {
			"labels": [_(label) for label, _value in chart_data],
			"datasets": [
				{
					"name": filters.price_list + " / " + (filters.get("item_group") or _("All Item Groups")),
					"values": [value for _label, value in chart_data],
				}
			],
		},
		"type": "donut" if view == "Coverage" else "line" if view == "Publication Trend" else "bar",
	}
	message = _(
		"Counts use permitted records in {0} / {1}. Coverage uses each Item's sales UOM (or stock UOM) and effective published prices. Review exceptions are saved calculated-revision results, including deselected rows; acknowledged margins with a meaningful review note are excluded from the review backlog. These are not live margin calculations. Draft/Calculated state is current, not historical. Published revision, fallback and cost-source counts use the last six calendar months; all outstanding drafts are included. Coverage is complete for the selected Price List / Item Group, up to 5,000 SKUs."
	).format(frappe.utils.escape_html(filters.company), frappe.utils.escape_html(filters.price_list))
	return columns, [row], message, None if metric else chart


def rule_counts(filters, config):
	counts = Counter()
	if not config.get("enable_phase_2"):
		return counts
	criteria = {"company": filters.company, "price_list": filters.price_list, "disabled": 0}
	if filters.get("supplier"):
		criteria["supplier"] = filters.supplier
	rows = read_rows(
		RULE,
		filters=criteria,
		fields=[
			"name",
			"item_code",
			"warehouse",
			"branch",
			"supplier",
			"item_group",
			"valid_from",
			"valid_upto",
		],
	)
	scope_items = catalog(filters) if filters.get("item_group") or filters.get("brand") else None
	item_ids = {item.name for item in scope_items} if scope_items is not None else None
	group_ids = (
		({item.item_group for item in scope_items} | {filters.item_group})
		if scope_items is not None and filters.get("include_child_groups")
		else {filters.get("item_group")}
	)
	links = (
		("item_code", "Item"),
		("warehouse", "Warehouse"),
		("branch", "Branch"),
		("supplier", "Supplier"),
		("item_group", "Item Group"),
	)
	allowed = {key: permitted_names(doctype, [row.get(key) for row in rows]) for key, doctype in links}
	for row in rows:
		if item_ids is not None and row.item_code and row.item_code not in item_ids:
			continue
		if not effective(row, getdate(filters.as_on)):
			continue
		if any(
			filters.get(key) and row.get(key) and row.get(key) != filters.get(key)
			for key in ("item_code", "warehouse", "branch", "supplier")
		):
			continue
		if filters.get("item_group") and row.item_group and row.item_group not in group_ids:
			continue
		if not all(not row.get(key) or row.get(key) in allowed[key] for key, _doctype in links):
			continue
		counts["supplier_rules"] += bool(row.supplier)
		counts["group_rules"] += bool(row.item_group)
	return counts


@frappe.whitelist()
def save_dashboard_scope(filters):
	values = frappe.parse_json(filters) if isinstance(filters, str) else filters
	values, _config = context({key: (values or {}).get(key) for key in SCOPE_FIELDS}, use_defaults=False)
	frappe.defaults.set_user_default(
		SCOPE_KEY, frappe.as_json({key: values.get(key) for key in SCOPE_FIELDS})
	)
	return {key: values.get(key) for key in SCOPE_FIELDS}


@frappe.whitelist()
def clear_dashboard_scope():
	frappe.has_permission(REVISION, "read", throw=True)
	frappe.defaults.set_user_default(SCOPE_KEY, "{}")
	return {"cleared": True}
