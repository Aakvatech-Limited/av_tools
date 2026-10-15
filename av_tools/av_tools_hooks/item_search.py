import json
import re

import frappe
from frappe import scrub
from frappe.desk.search import search_link as original_search_link
from frappe.desk.search import search_widget as original_search_widget
from frappe.query_builder.functions import IfNull
from frappe.utils import nowdate
from pypika import Case, CustomFunction

ERP_ITEM_QUERY = "erpnext.controllers.queries.item_query"
AV_TOOLS_ITEM_QUERY = "av_tools.av_tools_hooks.item_search.item_query"


def split_search_terms(txt: str | None) -> list[str]:
	if not txt or not isinstance(txt, str):
		return []

	return [part for part in re.split(r"\s+", txt.strip()) if part]


def route_item_query(doctype, query):
	if doctype == "Item" and not query:
		return AV_TOOLS_ITEM_QUERY

	if query == ERP_ITEM_QUERY:
		return AV_TOOLS_ITEM_QUERY

	return query


@frappe.whitelist()
def search_link(
	doctype: str,
	txt: str,
	query: str | None = None,
	filters: str | dict | list | None = None,
	page_length: int = 10,
	searchfield: str | None = None,
	reference_doctype: str | None = None,
	ignore_user_permissions: bool = False,
	*,
	link_fieldname: str | None = None,
):
	return original_search_link(
		doctype=doctype,
		txt=txt,
		query=route_item_query(doctype, query),
		filters=filters,
		page_length=page_length,
		searchfield=searchfield,
		reference_doctype=reference_doctype,
		ignore_user_permissions=ignore_user_permissions,
		link_fieldname=link_fieldname,
	)


@frappe.whitelist()
def search_widget(
	doctype: str,
	txt: str,
	query: str | None = None,
	searchfield: str | None = None,
	start: int = 0,
	page_length: int = 10,
	filters: str | dict | list | None = None,
	filter_fields: str | None = None,
	as_dict: bool = False,
	reference_doctype: str | None = None,
	ignore_user_permissions: bool = False,
	*,
	link_fieldname: str | None = None,
	for_link_validation: bool = False,
	query_filters_as_dict: bool = False,
):
	return original_search_widget(
		doctype=doctype,
		txt=txt,
		query=route_item_query(doctype, query),
		searchfield=searchfield,
		start=start,
		page_length=page_length,
		filters=filters,
		filter_fields=filter_fields,
		as_dict=as_dict,
		reference_doctype=reference_doctype,
		ignore_user_permissions=ignore_user_permissions,
		link_fieldname=link_fieldname,
		for_link_validation=for_link_validation,
		query_filters_as_dict=query_filters_as_dict,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def item_query(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: str | dict | list | None,
	as_dict: bool = False,
):
	doctype = "Item"
	search_terms = split_search_terms(txt)
	search_text = "%".join(search_terms) if search_terms else ""

	if isinstance(filters, str):
		filters = json.loads(filters)

	meta = frappe.get_meta(doctype, cached=True)
	searchfields = meta.get_search_fields()

	extra_searchfields = [field for field in searchfields if field not in ["name", "description"]]
	select_fields = ["name", *extra_searchfields]
	if "description" in searchfields:
		select_fields.append("description")

	searchfields = list(
		dict.fromkeys(
			searchfields
			+ [
				field
				for field in [searchfield or "name", "item_code", "item_group", "item_name"]
				if field not in searchfields
			]
		)
	)

	if filters and isinstance(filters, dict):
		if filters.get("customer") or filters.get("supplier"):
			party = filters.get("customer") or filters.get("supplier")
			item_rules_list = frappe.get_all(
				"Party Specific Item",
				filters={"party": party},
				fields=["restrict_based_on", "based_on_value"],
			)

			filters_dict = {}
			for rule in item_rules_list:
				if rule["restrict_based_on"] == "Item":
					rule["restrict_based_on"] = "name"
				filters_dict[rule.restrict_based_on] = []

			for rule in item_rules_list:
				filters_dict[rule.restrict_based_on].append(rule.based_on_value)

			for filter in filters_dict:
				filters[scrub(filter)] = ["in", filters_dict[filter]]

			if filters.get("customer"):
				del filters["customer"]
			else:
				del filters["supplier"]
		else:
			filters.pop("customer", None)
			filters.pop("supplier", None)

	Item = frappe.qb.DocType("Item")
	Barcode = frappe.qb.DocType("Item Barcode")
	query = frappe.qb.get_query(
		"Item",
		fields=select_fields,
		filters=filters,
		ignore_permissions=False,
	)
	query = (
		query.where(Item.docstatus < 2)
		.where(Item.disabled == 0)
		.where(Item.has_variants == 0)
		.where((Item.end_of_life > nowdate()) | (IfNull(Item.end_of_life, "0000-00-00") == "0000-00-00"))
	)

	def matches_terms(field):
		if len(search_terms) <= 1:
			return field.like(f"%{search_text}%")
		criterion = field.like(f"%{search_terms[0]}%")
		for term in search_terms[1:]:
			criterion = criterion & field.like(f"%{term}%")
		return criterion

	search_condition = None
	for fieldname in searchfields:
		criterion = matches_terms(Item[fieldname])
		search_condition = criterion if search_condition is None else search_condition | criterion

	barcode_query = (
		frappe.qb.from_(Barcode).select(Barcode.parent).where(Barcode.barcode.like(f"%{search_text}%"))
	)
	search_condition = search_condition | Item.item_code.isin(barcode_query)
	if frappe.db.count(doctype, cache=True) < 50000:
		search_condition = search_condition | matches_terms(Item.description)
	query = query.where(search_condition)

	Locate = CustomFunction("LOCATE", ["needle", "haystack"])
	first_term = (search_terms[0] if search_terms else "").replace("%", "")
	for field in (Item.name, Item.item_name):
		rank = Locate(first_term, field)
		query = query.orderby(Case().when(rank > 0, rank).else_(99999))
	query = query.orderby(Item.idx, order=frappe.qb.desc).orderby(Item.name).orderby(Item.item_name)
	query = query.offset(start).limit(page_len)
	rows = query.run(as_dict=True)
	if "description" in select_fields:
		for row in rows:
			if row.get("description") and len(row.description) > 40:
				row.description = row.description[:40] + "..."
	if as_dict:
		return rows
	return [tuple(row.get(field) for field in select_fields) for row in rows]
