import frappe
from frappe.utils import flt
from frappe.query_builder.functions import Coalesce
from frappe.query_builder.terms import ConstantColumn
from pypika import Case


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns(filters)
	rows = get_rows(filters)

	if filters.get("view") == "Grouped by Customer":
		rows = group_by_customer(rows)

	# Differences MUST ALWAYS be in company currency
	for r in rows:
		r["ordered_minus_received"] = flt(r.get("ordered_amount_company")) - flt(
			r.get("received_amount_company")
		)
		r["ordered_minus_billed"] = flt(r.get("ordered_amount_company")) - flt(r.get("billed_amount_company"))
		r["billed_minus_received"] = flt(r.get("billed_amount_company")) - flt(
			r.get("received_amount_company")
		)

	return columns, rows


def validate_filters(filters):
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw("From Date and To Date are required.")

	if filters.from_date > filters.to_date:
		frappe.throw("From Date cannot be after To Date.")


def get_columns(filters):
	currency_fields = [
		{
			"label": "Ordered Amount (Txn)",
			"fieldname": "ordered_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": "Ordered Amount (Company)",
			"fieldname": "ordered_amount_company",
			"fieldtype": "Currency",
			"options": "company_currency",
			"width": 170,
		},
		{
			"label": "Received Amount (Txn)",
			"fieldname": "received_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": "Received Amount (Company)",
			"fieldname": "received_amount_company",
			"fieldtype": "Currency",
			"options": "company_currency",
			"width": 170,
		},
		{
			"label": "Billed Amount (Txn)",
			"fieldname": "billed_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": "Billed Amount (Company)",
			"fieldname": "billed_amount_company",
			"fieldtype": "Currency",
			"options": "company_currency",
			"width": 170,
		},
		# IMPORTANT: Differences ALWAYS in company currency
		{
			"label": "Ordered - Received (Company)",
			"fieldname": "ordered_minus_received",
			"fieldtype": "Currency",
			"options": "company_currency",
			"width": 190,
		},
		{
			"label": "Ordered - Billed (Company)",
			"fieldname": "ordered_minus_billed",
			"fieldtype": "Currency",
			"options": "company_currency",
			"width": 190,
		},
		{
			"label": "Billed - Received (Company)",
			"fieldname": "billed_minus_received",
			"fieldtype": "Currency",
			"options": "company_currency",
			"width": 190,
		},
	]

	return [
		{
			"label": "Customer",
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 180,
		},
		{"label": "Doc Type", "fieldname": "doc_type", "fieldtype": "Data", "width": 130},
		{
			"label": "Doc No",
			"fieldname": "doc_no",
			"fieldtype": "Dynamic Link",
			"options": "doc_type",
			"width": 180,
		},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": "Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{
			"label": "Currency",
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"width": 90,
		},
		{
			"label": "Company Currency",
			"fieldname": "company_currency",
			"fieldtype": "Link",
			"options": "Currency",
			"width": 120,
		},
		{"label": "Exchange Rate", "fieldname": "exchange_rate", "fieldtype": "Float", "width": 110},
		{
			"label": "Item Code",
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 140,
		},
		{"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		*currency_fields,
	]


def get_rows(filters):
	company = filters.get("company") or frappe.defaults.get_user_default("Company")
	company_currency = frappe.get_cached_value("Company", company, "default_currency")

	rows = []

	# Sales Order lines + tax row(s)
	rows.extend(get_sales_order_rows(filters, company_currency))
	rows.extend(get_sales_order_tax_rows(filters, company_currency))

	# Sales Invoice lines + tax row(s)
	rows.extend(get_sales_invoice_rows(filters, company_currency))
	rows.extend(get_sales_invoice_tax_rows(filters, company_currency))

	# Payments
	rows.extend(get_payment_rows(filters, company_currency))

	rows.sort(key=lambda r: (r.get("posting_date") or "", r.get("doc_type") or "", r.get("doc_no") or ""))
	return rows


def _filter_query(query, doc, date_field, filters):
	query = query.where(doc[date_field].between(filters.from_date, filters.to_date))
	if filters.get("customer"):
		query = query.where(doc.customer == filters.customer) if date_field != "payment" else query
	if filters.get("company"):
		query = query.where(doc.company == filters.company)
	return query


def _sales_rows(filters, company_currency, doctype, tax=False):
	doc = frappe.qb.DocType(doctype)
	is_order = doctype == "Sales Order"
	date_field = "transaction_date" if is_order else "posting_date"
	query = frappe.qb.from_(doc)
	if not tax:
		child = frappe.qb.DocType(doctype + " Item")
		query = query.join(child).on(child.parent == doc.name)
	else:
		query = query.where(Coalesce(doc.total_taxes_and_charges, 0) != 0)
	amount = doc.total_taxes_and_charges if tax else child.net_amount
	base_amount = doc.base_total_taxes_and_charges if tax else child.base_net_amount
	if is_order:
		factor = Coalesce(doc.per_billed, 0) / 100
		amount = Case().when(doc.status == "Closed", amount * factor).else_(amount)
		base_amount = Case().when(doc.status == "Closed", base_amount * factor).else_(base_amount)
	query = query.select(
		doc.customer.as_("customer"), ConstantColumn(doctype).as_("doc_type"),
		doc.name.as_("doc_no"), doc.status,
		doc[date_field].as_("posting_date"), doc.currency,
		ConstantColumn(company_currency).as_("company_currency"), doc.conversion_rate.as_("exchange_rate"),
		(ConstantColumn(None) if tax else child.item_code).as_("item_code"),
		(ConstantColumn("TOTAL TAXES AND CHARGES") if tax else child.item_name).as_("item_name"),
		(amount if is_order else ConstantColumn(0)).as_("ordered_amount"),
		(base_amount if is_order else ConstantColumn(0)).as_("ordered_amount_company"),
		ConstantColumn(0).as_("received_amount"), ConstantColumn(0).as_("received_amount_company"),
		(amount if not is_order else ConstantColumn(0)).as_("billed_amount"),
		(base_amount if not is_order else ConstantColumn(0)).as_("billed_amount_company"),
	).where(doc.docstatus == 1)
	return _filter_query(query, doc, date_field, filters).run(as_dict=True)


def get_sales_order_rows(filters, company_currency):
	return _sales_rows(filters, company_currency, "Sales Order")


def get_sales_order_tax_rows(filters, company_currency):
	return _sales_rows(filters, company_currency, "Sales Order", tax=True)


def get_sales_invoice_rows(filters, company_currency):
	return _sales_rows(filters, company_currency, "Sales Invoice")


def get_sales_invoice_tax_rows(filters, company_currency):
	return _sales_rows(filters, company_currency, "Sales Invoice", tax=True)


def get_payment_rows(filters, company_currency):
	pe = frappe.qb.DocType("Payment Entry")
	ref = frappe.qb.DocType("Payment Entry Reference")
	signed = Case().when(pe.payment_type == "Receive", ref.allocated_amount).when(
		pe.payment_type == "Pay", -ref.allocated_amount
	).else_(0)
	query = (
		frappe.qb.from_(pe).join(ref).on(ref.parent == pe.name)
		.select(
			pe.party.as_("customer"), ConstantColumn("Payment Entry").as_("doc_type"),
			pe.name.as_("doc_no"), pe.status, pe.posting_date,
			pe.paid_from_account_currency.as_("currency"),
			ConstantColumn(company_currency).as_("company_currency"),
			pe.source_exchange_rate.as_("exchange_rate"),
			ConstantColumn(None).as_("item_code"), ConstantColumn(None).as_("item_name"),
			ConstantColumn(0).as_("ordered_amount"),
			ConstantColumn(0).as_("ordered_amount_company"),
			signed.as_("received_amount"),
			(signed * Coalesce(pe.source_exchange_rate, 1)).as_("received_amount_company"),
			ConstantColumn(0).as_("billed_amount"),
			ConstantColumn(0).as_("billed_amount_company"),
		)
		.where((pe.docstatus == 1) & (pe.party_type == "Customer") & (ref.reference_doctype == "Sales Invoice"))
		.where(pe.posting_date.between(filters.from_date, filters.to_date))
	)
	if filters.get("customer"):
		query = query.where(pe.party == filters.customer)
	if filters.get("company"):
		query = query.where(pe.company == filters.company)
	return query.run(as_dict=True)


def group_by_customer(rows):
	grouped = {}

	for r in rows:
		key = r.get("customer") or ""
		if key not in grouped:
			grouped[key] = {
				"customer": r.get("customer"),
				"doc_type": "Grouped",
				"doc_no": None,
				"posting_date": None,
				"currency": None,
				"company_currency": r.get("company_currency"),
				"exchange_rate": None,
				"item_code": None,
				"item_name": None,
				"ordered_amount": 0,
				"ordered_amount_company": 0,
				"received_amount": 0,
				"received_amount_company": 0,
				"billed_amount": 0,
				"billed_amount_company": 0,
			}

		g = grouped[key]
		g["ordered_amount"] += flt(r.get("ordered_amount"))
		g["ordered_amount_company"] += flt(r.get("ordered_amount_company"))
		g["received_amount"] += flt(r.get("received_amount"))
		g["received_amount_company"] += flt(r.get("received_amount_company"))
		g["billed_amount"] += flt(r.get("billed_amount"))
		g["billed_amount_company"] += flt(r.get("billed_amount_company"))

	return list(grouped.values())
