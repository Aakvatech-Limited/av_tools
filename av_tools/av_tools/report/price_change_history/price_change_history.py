# Copyright (c) 2024, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns(filters)

	data = get_data(filters)

	if len(data) == 0:
		frappe.msgprint("<strong>No record found, Please check you filters</strong>")
		return

	return columns, data


def get_data(filters):
	Request = frappe.qb.DocType("Price Change Request")
	Detail = frappe.qb.DocType("Price Change Request Detail")
	query = (
		frappe.qb.from_(Request)
		.join(Detail)
		.on(Request.name == Detail.parent)
		.select(
			Request.posting_date.as_("date"),
			Detail.item_code,
			Detail.item_name,
			Detail.price_list,
			Detail.old_price,
			Detail.new_price,
		)
		.where(Request.docstatus == 1)
		.where(Request.company == filters.get("company"))
	)

	if filters.get("item"):
		query = query.where(Detail.item_code == filters.get("item"))
	if filters.get("price_list"):
		query = query.where(Detail.price_list == filters.get("price_list"))
	if filters.get("from_date"):
		query = query.where(Request.posting_date >= filters.get("from_date"))
	if filters.get("to_date"):
		query = query.where(Request.posting_date <= filters.get("to_date"))

	return query.run(as_dict=True)


def get_columns(filters):
	return [
		{"fieldname": "date", "fieldtype": "Date", "label": _("Date"), "width": "110px"},
		{
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"label": _("Item Code"),
			"width": "170px",
		},
		{"fieldname": "item_name", "fieldtype": "Data", "label": _("Item Name"), "width": "200px"},
		{
			"fieldname": "price_list",
			"fieldtype": "Link",
			"options": "Price List",
			"label": _("Price List"),
			"width": "170px",
		},
		{"fieldname": "old_price", "fieldtype": "Currency", "label": _("Old Price"), "width": "100px"},
		{"fieldname": "new_price", "fieldtype": "Currency", "label": _("New Price"), "width": "100px"},
	]
