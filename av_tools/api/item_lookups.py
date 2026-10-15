from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

DEFAULT_MAX_RECORDS = 20


def _get_stock_ledger_entries(item_code: str) -> list[dict]:
	return frappe.db.sql(
		"""
		SELECT sle.batch_no, sle.item_code, sle.warehouse,
		       sle.qty_after_transaction AS actual_qty
		FROM `tabStock Ledger Entry` sle
		INNER JOIN (
			SELECT IF(batch_no IS NULL, '', batch_no) AS batch_no,
			       item_code, warehouse,
			       MAX(posting_datetime) AS posting_datetime
			FROM `tabStock Ledger Entry`
			GROUP BY IF(batch_no IS NULL, '', batch_no), item_code, warehouse
		) AS sle_max
			ON IF(sle.batch_no IS NULL, '', sle.batch_no) = sle_max.batch_no
			AND sle.item_code = sle_max.item_code
			AND sle.warehouse = sle_max.warehouse
			AND sle.posting_datetime = sle_max.posting_datetime
		WHERE sle.docstatus = 1
		  AND sle.is_cancelled = 0
		  AND sle.item_code = %(item_code)s
		ORDER BY sle.warehouse, sle.item_code, sle.batch_no
		""",
		{"item_code": item_code},
		as_dict=1,
	)


@frappe.whitelist()
def get_item_info(item_code: Any):
	"""Return per-(warehouse, batch) on-hand balance for an item, with batch expiry data."""
	sle = _get_stock_ledger_entries(item_code)
	iwb_map: dict = {}
	float_precision = cint(frappe.db.get_default("float_precision")) or 3

	for d in sle:
		iwb_map.setdefault(d.item_code, {}).setdefault(d.warehouse, {}).setdefault(
			d.batch_no, frappe._dict({"bal_qty": 0.0})
		)
		qty_dict = iwb_map[d.item_code][d.warehouse][d.batch_no]

		expiry_date = frappe.db.get_value("Batch", d.batch_no, "expiry_date") if d.batch_no else None
		if expiry_date:
			exp_date = frappe.utils.data.getdate(expiry_date)
			qty_dict.expires_on = exp_date
			expires_in_days = (exp_date - frappe.utils.datetime.date.today()).days
			qty_dict.expiry_status = expires_in_days if expires_in_days > 0 else 0

		qty_dict.actual_qty = flt(qty_dict.actual_qty, float_precision) + flt(d.actual_qty, float_precision)

	result = []
	for item_code_key, warehouses in iwb_map.items():
		for warehouse, batches in warehouses.items():
			for batch_no, qty_dict in batches.items():
				row = {"item_code": item_code_key, "warehouse": warehouse, "batch_no": batch_no}
				row.update(qty_dict)
				result.append(row)
	return result


def _get_invoice_prices(invoice_type, item_code, currency, company, party=None, posting_date_range=None):
	"""Fetch invoice item prices with safely bound Query Builder predicates."""
	parent_doctype = "Sales Invoice" if invoice_type == "Sales" else "Purchase Invoice"
	item_doctype = parent_doctype + " Item"
	Invoice = frappe.qb.DocType(parent_doctype)
	Item = frappe.qb.DocType(item_doctype)
	party_field = Invoice.customer if invoice_type == "Sales" else Invoice.supplier
	query = (
		frappe.qb.from_(Invoice)
		.join(Item)
		.on(Item.parent == Invoice.name)
		.select(Invoice.name, Invoice.posting_date, party_field, Item.item_code, Item.qty, Item.rate)
		.where(Item.item_code == item_code)
		.where(Invoice.docstatus == 1)
		.where(Invoice.currency == currency)
		.where(Invoice.is_return != 1)
		.where(Invoice.company == company)
	)
	if party:
		query = query.where(party_field == party)
	if posting_date_range and isinstance(posting_date_range, (list, tuple)) and len(posting_date_range) > 1:
		try:
			from_date, to_date = posting_date_range[1][0], posting_date_range[1][1]
			query = query.where(Invoice.posting_date.between(from_date, to_date))
		except (IndexError, TypeError):
			pass
	return query.orderby(Invoice.posting_date, order=frappe.qb.desc).run(as_dict=True)


def _collect_prices(rows: list[dict], rate_field: str, mapper, max_records: int) -> list[dict]:
	prices: list[dict] = []
	for row in rows:
		if row.get(rate_field) and len(prices) < max_records:
			prices.append(mapper(row))
	return prices


@frappe.whitelist()
def get_item_prices(item_code: Any, currency: Any, customer: Any = None, company: Any = None):
	"""Sales Invoice historical prices for an item (legacy shape: `price`, `date`)."""
	rows = _get_invoice_prices("Sales", item_code, currency, company, party=customer)
	return _collect_prices(
		rows,
		"rate",
		lambda r: {
			"name": r.item_code,
			"item_code": r.item_code,
			"price": r.rate,
			"date": r.posting_date,
			"invoice": r.name,
			"customer": r.customer,
			"qty": r.qty,
		},
		DEFAULT_MAX_RECORDS,
	)


@frappe.whitelist()
def get_item_prices_custom(filters: Any = None, start: Any = 0, limit: Any = 20):
	"""Sales Invoice historical prices for an item (Ctrl+I shape: `rate`, `posting_date`)."""
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except json.JSONDecodeError:
			frappe.throw(_("Invalid format for filters. Ensure it's a valid JSON object."))
	filters = filters or {}

	customer = filters.get("customer", "")
	company = filters.get("company", "")
	item_code = filters.get("item_code", "")
	currency = filters.get("currency", "")
	posting_date_range = filters.get("posting_date")
	max_records = int(start) + int(limit)

	rows = _get_invoice_prices("Sales", item_code, currency, company, party=customer, posting_date_range=posting_date_range)
	return _collect_prices(
		rows,
		"rate",
		lambda r: {
			"name": r.item_code,
			"item_code": r.item_code,
			"rate": r.rate,
			"posting_date": r.posting_date,
			"invoice": r.name,
			"customer": r.customer,
			"qty": r.qty,
		},
		max_records,
	)


@frappe.whitelist()
def get_item_prices_custom_po(filters: Any = None, start: Any = 0, limit: Any = 20):
	"""Purchase Invoice historical prices for an item (Ctrl+I on PO shape)."""
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except json.JSONDecodeError:
			frappe.throw(_("Invalid format for filters. Ensure it's a valid JSON object."))
	filters = filters or {}

	supplier = filters.get("customer", "")
	company = filters.get("company", "")
	item_code = filters.get("item_code", "")
	currency = filters.get("currency", "")
	posting_date_range = filters.get("posting_date")
	max_records = int(start) + int(limit)

	rows = _get_invoice_prices("Purchase", item_code, currency, company, party=supplier, posting_date_range=posting_date_range)
	return _collect_prices(
		rows,
		"rate",
		lambda r: {
			"name": r.item_code,
			"item_code": r.item_code,
			"rate": r.rate,
			"posting_date": r.posting_date,
			"invoice": r.name,
			"customer": r.supplier,
			"qty": r.qty,
		},
		max_records,
	)


@frappe.whitelist()
def get_item_prices_po(item_code: Any, currency: Any, customer: Any = None, company: Any = None):
	"""Purchase Invoice historical prices (legacy PO shape: `price`, `date`)."""
	rows = _get_invoice_prices("Purchase", item_code, currency, company, party=customer)
	return _collect_prices(
		rows,
		"rate",
		lambda r: {
			"name": r.item_code,
			"item_code": r.item_code,
			"price": r.rate,
			"date": r.posting_date,
			"invoice": r.name,
			"customer": r.supplier,
			"qty": r.qty,
		},
		DEFAULT_MAX_RECORDS,
	)
