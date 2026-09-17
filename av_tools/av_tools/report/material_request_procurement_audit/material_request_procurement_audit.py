# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = get_date_range(filters)
	columns = get_columns()
	data = get_data(filters, from_date, to_date)
	return columns, data


def get_date_range(filters):
	time_span = filters.get("time_span") or "This Month"
	current_date = today()
	from_date = None
	to_date = None

	if time_span == "Today":
		from_date = current_date
		to_date = current_date
	elif time_span == "Yesterday":
		from_date = add_days(current_date, -1)
		to_date = from_date
	elif time_span == "This Week":
		weekday_number = getdate(current_date).weekday()
		from_date = add_days(current_date, -weekday_number)
		to_date = add_days(from_date, 6)
	elif time_span == "Last Week":
		weekday_number = getdate(current_date).weekday()
		this_week_start = add_days(current_date, -weekday_number)
		from_date = add_days(this_week_start, -7)
		to_date = add_days(this_week_start, -1)
	elif time_span == "This Month":
		from_date = get_first_day(current_date)
		to_date = get_last_day(current_date)
	elif time_span == "Last Month":
		previous_month = add_months(current_date, -1)
		from_date = get_first_day(previous_month)
		to_date = get_last_day(previous_month)
	elif time_span == "This Year":
		current_year = getdate(current_date).year
		from_date = f"{current_year}-01-01"
		to_date = f"{current_year}-12-31"
	elif time_span == "Last Year":
		previous_year = getdate(current_date).year - 1
		from_date = f"{previous_year}-01-01"
		to_date = f"{previous_year}-12-31"
	elif time_span == "Period":
		from_date = filters.get("from_date")
		to_date = filters.get("to_date")

	return from_date, to_date


def get_columns():
	return [
		{"label": _("Material Request"), "fieldname": "material_request", "fieldtype": "Link", "options": "Material Request", "width": 170},
		{"label": _("MR Date"), "fieldname": "material_request_date", "fieldtype": "Date", "width": 100},
		{"label": _("Required By"), "fieldname": "schedule_date", "fieldtype": "Date", "width": 100},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 160},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 140},
		{"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Requested Qty"), "fieldname": "requested_qty", "fieldtype": "Float", "width": 115},
		{"label": _("Ordered Qty"), "fieldname": "ordered_qty", "fieldtype": "Float", "width": 110},
		{"label": _("PO Audit Qty"), "fieldname": "po_audit_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Pending to Order"), "fieldname": "pending_to_order", "fieldtype": "Float", "width": 120},
		{"label": _("Order Variance"), "fieldname": "order_variance", "fieldtype": "Float", "width": 110},
		{"label": _("PO Audit Difference"), "fieldname": "po_audit_difference", "fieldtype": "Float", "width": 125},
		{"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 110},
		{"label": _("PR Accepted Qty"), "fieldname": "pr_received_qty", "fieldtype": "Float", "width": 115},
		{"label": _("PI Update Stock Qty"), "fieldname": "pi_stock_qty", "fieldtype": "Float", "width": 125},
		{"label": _("Traced Received Qty"), "fieldname": "traced_received_qty", "fieldtype": "Float", "width": 125},
		{"label": _("Rejected Qty"), "fieldname": "rejected_qty", "fieldtype": "Float", "width": 105},
		{"label": _("Pending to Receive"), "fieldname": "pending_to_receive", "fieldtype": "Float", "width": 125},
		{"label": _("Request Not Received"), "fieldname": "request_not_received", "fieldtype": "Float", "width": 130},
		{"label": _("Receipt Variance"), "fieldname": "receipt_variance", "fieldtype": "Float", "width": 115},
		{"label": _("Receipt Audit Difference"), "fieldname": "receipt_audit_difference", "fieldtype": "Float", "width": 135},
		{"label": _("Suppliers"), "fieldname": "suppliers", "fieldtype": "Data", "width": 180},
		{"label": _("Purchase Orders"), "fieldname": "purchase_orders", "fieldtype": "Data", "width": 220},
		{"label": _("Purchase Receipts"), "fieldname": "purchase_receipts", "fieldtype": "Data", "width": 220},
		{"label": _("Stock Purchase Invoices"), "fieldname": "stock_purchase_invoices", "fieldtype": "Data", "width": 220},
		{"label": _("Procurement Status"), "fieldname": "procurement_status", "fieldtype": "Data", "width": 150},
		{"label": _("Audit Exception"), "fieldname": "audit_exception", "fieldtype": "Data", "width": 220},
		{"label": _("MR Item ID"), "fieldname": "material_request_item", "fieldtype": "Data", "width": 140},
	]


def get_data(filters, from_date, to_date):
	mr_filters = {
		"docstatus": 1,
		"material_request_type": "Purchase",
	}

	if filters.get("company"):
		mr_filters["company"] = filters.get("company")
	if filters.get("material_request"):
		mr_filters["name"] = filters.get("material_request")
	if from_date and to_date:
		mr_filters["transaction_date"] = ["between", [from_date, to_date]]
	elif from_date:
		mr_filters["transaction_date"] = [">=", from_date]
	elif to_date:
		mr_filters["transaction_date"] = ["<=", to_date]

	mr_rows = frappe.get_all(
		"Material Request",
		filters=mr_filters,
		fields=["name", "transaction_date", "company", "status"],
		order_by="transaction_date asc, name asc",
	)

	if not mr_rows:
		return []

	mr_names = [row.name for row in mr_rows]
	mr_map = {row.name: row for row in mr_rows}

	mri_filters = {"parent": ["in", mr_names]}
	if filters.get("item_code"):
		mri_filters["item_code"] = filters.get("item_code")
	if filters.get("warehouse"):
		mri_filters["warehouse"] = filters.get("warehouse")
	if filters.get("project"):
		mri_filters["project"] = filters.get("project")

	mr_item_rows = frappe.get_all(
		"Material Request Item",
		filters=mri_filters,
		fields=[
			"name",
			"parent",
			"idx",
			"item_code",
			"item_name",
			"schedule_date",
			"warehouse",
			"project",
			"stock_uom",
			"stock_qty",
			"ordered_qty",
			"received_qty",
		],
		order_by="parent asc, idx asc",
	)

	if not mr_item_rows:
		return []

	mr_item_names = [row.name for row in mr_item_rows]

	po_item_rows = frappe.get_all(
		"Purchase Order Item",
		filters={"material_request_item": ["in", mr_item_names]},
		fields=["name", "parent", "material_request_item", "stock_qty"],
	)
	po_names = list({row.parent for row in po_item_rows if row.parent})
	po_map = {}
	if po_names:
		for row in frappe.get_all(
			"Purchase Order",
			filters={"name": ["in", po_names], "docstatus": 1},
			fields=["name", "supplier", "transaction_date", "status"],
		):
			po_map[row.name] = row

	po_audit_map = {}
	po_item_to_mri = {}
	valid_po_item_names = []
	for row in po_item_rows:
		if row.parent not in po_map:
			continue
		mri_name = row.material_request_item
		entry = po_audit_map.setdefault(mri_name, {"qty": 0.0, "purchase_orders": [], "suppliers": []})
		entry["qty"] += flt(row.stock_qty)
		if row.parent not in entry["purchase_orders"]:
			entry["purchase_orders"].append(row.parent)
		supplier = po_map[row.parent].supplier
		if supplier and supplier not in entry["suppliers"]:
			entry["suppliers"].append(supplier)
		po_item_to_mri[row.name] = mri_name
		valid_po_item_names.append(row.name)

	pr_audit_map = {}
	if valid_po_item_names:
		pr_item_rows = frappe.get_all(
			"Purchase Receipt Item",
			filters={"purchase_order_item": ["in", valid_po_item_names]},
			fields=["name", "parent", "purchase_order_item", "stock_qty", "rejected_qty", "conversion_factor"],
		)
		pr_names = list({row.parent for row in pr_item_rows if row.parent})
		pr_map = {}
		if pr_names:
			for row in frappe.get_all(
				"Purchase Receipt",
				filters={"name": ["in", pr_names], "docstatus": 1},
				fields=["name", "posting_date", "supplier", "is_return"],
			):
				pr_map[row.name] = row

		for row in pr_item_rows:
			if row.parent not in pr_map or row.purchase_order_item not in po_item_to_mri:
				continue
			mri_name = po_item_to_mri[row.purchase_order_item]
			entry = pr_audit_map.setdefault(mri_name, {"received_qty": 0.0, "rejected_qty": 0.0, "purchase_receipts": []})
			entry["received_qty"] += flt(row.stock_qty)
			entry["rejected_qty"] += flt(row.rejected_qty) * flt(row.conversion_factor)
			if row.parent not in entry["purchase_receipts"]:
				entry["purchase_receipts"].append(row.parent)

	pi_audit_map = {}
	pi_item_rows = frappe.get_all(
		"Purchase Invoice Item",
		filters={"material_request_item": ["in", mr_item_names]},
		fields=["name", "parent", "material_request_item", "stock_qty", "purchase_receipt"],
	)
	pi_names = list({row.parent for row in pi_item_rows if row.parent})
	pi_map = {}
	if pi_names:
		for row in frappe.get_all(
			"Purchase Invoice",
			filters={"name": ["in", pi_names], "docstatus": 1, "update_stock": 1},
			fields=["name", "posting_date", "supplier", "is_return"],
		):
			pi_map[row.name] = row

	for row in pi_item_rows:
		if row.parent not in pi_map or row.purchase_receipt:
			continue
		mri_name = row.material_request_item
		entry = pi_audit_map.setdefault(mri_name, {"stock_qty": 0.0, "purchase_invoices": []})
		entry["stock_qty"] += flt(row.stock_qty)
		if row.parent not in entry["purchase_invoices"]:
			entry["purchase_invoices"].append(row.parent)

	data = []
	tolerance = 0.000001
	selected_status = filters.get("procurement_status")
	show_only_exceptions = filters.get("show_only_exceptions")

	for row in mr_item_rows:
		mr = mr_map.get(row.parent)
		if not mr:
			continue

		requested_qty = flt(row.stock_qty)
		ordered_qty = flt(row.ordered_qty)
		received_qty = flt(row.received_qty)

		po_entry = po_audit_map.get(row.name, {})
		pr_entry = pr_audit_map.get(row.name, {})
		pi_entry = pi_audit_map.get(row.name, {})

		po_audit_qty = flt(po_entry.get("qty"))
		pr_received_qty = flt(pr_entry.get("received_qty"))
		rejected_qty = flt(pr_entry.get("rejected_qty"))
		pi_stock_qty = flt(pi_entry.get("stock_qty"))
		traced_received_qty = pr_received_qty + pi_stock_qty

		pending_to_order = max(requested_qty - ordered_qty, 0)
		pending_to_receive = max(ordered_qty - received_qty, 0)
		request_not_received = max(requested_qty - received_qty, 0)
		order_variance = ordered_qty - requested_qty
		receipt_variance = received_qty - ordered_qty
		po_audit_difference = ordered_qty - po_audit_qty
		receipt_audit_difference = received_qty - traced_received_qty

		procurement_status = "Not Ordered"
		if received_qty > requested_qty + tolerance or received_qty > ordered_qty + tolerance:
			procurement_status = "Over Received"
		elif ordered_qty > requested_qty + tolerance:
			procurement_status = "Over Ordered"
		elif received_qty >= requested_qty - tolerance:
			procurement_status = "Fully Received"
		elif received_qty > tolerance:
			procurement_status = "Partly Received"
		elif ordered_qty >= requested_qty - tolerance:
			procurement_status = "Fully Ordered"
		elif ordered_qty > tolerance:
			procurement_status = "Partly Ordered"

		exceptions = []
		if abs(po_audit_difference) > tolerance:
			exceptions.append(_("Ordered Qty differs from linked submitted POs"))
		if abs(receipt_audit_difference) > tolerance:
			exceptions.append(_("Received Qty differs from traced stock receipts"))
		if ordered_qty > requested_qty + tolerance:
			exceptions.append(_("Ordered above requested quantity"))
		if received_qty > ordered_qty + tolerance:
			exceptions.append(_("Received above ordered quantity"))
		if received_qty > requested_qty + tolerance:
			exceptions.append(_("Received above requested quantity"))
		if abs(rejected_qty) > tolerance:
			exceptions.append(_("Rejected quantity exists"))

		if selected_status and selected_status != "All" and procurement_status != selected_status:
			continue
		if show_only_exceptions and not exceptions:
			continue

		data.append(
			{
				"material_request": row.parent,
				"material_request_item": row.name,
				"material_request_date": mr.transaction_date,
				"schedule_date": row.schedule_date,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"warehouse": row.warehouse,
				"project": row.project,
				"stock_uom": row.stock_uom,
				"requested_qty": requested_qty,
				"ordered_qty": ordered_qty,
				"po_audit_qty": po_audit_qty,
				"pending_to_order": pending_to_order,
				"order_variance": order_variance,
				"po_audit_difference": po_audit_difference,
				"received_qty": received_qty,
				"pr_received_qty": pr_received_qty,
				"pi_stock_qty": pi_stock_qty,
				"traced_received_qty": traced_received_qty,
				"rejected_qty": rejected_qty,
				"pending_to_receive": pending_to_receive,
				"request_not_received": request_not_received,
				"receipt_variance": receipt_variance,
				"receipt_audit_difference": receipt_audit_difference,
				"suppliers": ", ".join(po_entry.get("suppliers", [])),
				"purchase_orders": ", ".join(po_entry.get("purchase_orders", [])),
				"purchase_receipts": ", ".join(pr_entry.get("purchase_receipts", [])),
				"stock_purchase_invoices": ", ".join(pi_entry.get("purchase_invoices", [])),
				"procurement_status": procurement_status,
				"audit_exception": "; ".join(exceptions),
			}
		)

	return data
