"""Expanded policy context and permission-aware bulk Item filtering."""

import frappe

from av_tools.selling_pricing_engine.access import check_link


def groups(item_group):
	result = []
	while item_group:
		if item_group in result:
			raise ValueError("Cyclic Item Group hierarchy")
		result.append(item_group)
		item_group = frappe.get_cached_value("Item Group", item_group, "parent_item_group")
	return result


def check_filters(doc):
	for key, doctype in (
		("supplier", "Supplier"),
		("item_group", "Item Group"),
		("brand", "Brand"),
		("branch", "Branch"),
	):
		check_link(doctype, doc.get(key))
	if doc.get("source_document"):
		if doc.get("source_doctype") not in ("Purchase Invoice", "Purchase Receipt"):
			raise ValueError("Select Purchase Invoice or Purchase Receipt for the current cost source")
		frappe.has_permission(doc.source_doctype, "read", doc=doc.source_document, throw=True)


def item_filters(doc):
	check_filters(doc)
	criteria = {"disabled": 0, "is_sales_item": 1, "has_variants": 0, "is_fixed_asset": 0}
	if doc.get("item_code"):
		criteria["name"] = doc.get("item_code")
	if doc.get("brand"):
		criteria["brand"] = doc.get("brand")
	if doc.get("item_group"):
		if doc.get("include_child_groups"):
			group = frappe.get_cached_doc("Item Group", doc.get("item_group"))
			permitted = frappe.get_list(
				"Item Group",
				filters={"lft": [">=", group.lft], "rgt": ["<=", group.rgt]},
				pluck="name",
				limit_page_length=0,
			)
			criteria["item_group"] = ["in", permitted]
		else:
			criteria["item_group"] = doc.get("item_group")
	return criteria
