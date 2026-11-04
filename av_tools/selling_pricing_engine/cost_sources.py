"""Submitted procurement and dated ledger costs; never update stock valuation."""

import frappe
from frappe.utils import add_days, getdate

from av_tools.selling_pricing_engine import repository
from av_tools.selling_pricing_engine.calculation import number

SOURCES = (
	"Latest Submitted Purchase Invoice",
	"Current Purchase Invoice",
	"Current Purchase Receipt",
	"Latest Submitted Purchase Receipt",
	"Latest Purchase Rate",
	"Supplier Latest Purchase Rate",
	"Valuation Rate",
	"Warehouse Valuation Rate",
)


def cost(company, item, uom, currency, date, basis, context, *, fallbacks=None, lock=False):
	attempts = []
	chain = [basis, *[line.strip() for line in (fallbacks or "").splitlines() if line.strip()]]
	for source in dict.fromkeys(chain):
		if source not in SOURCES:
			raise ValueError("Unsupported cost source: " + str(source))
		try:
			if source in ("Valuation Rate", "Warehouse Valuation Rate"):
				result = valuation(company, item, uom, currency, date, context.get("warehouse"), lock=lock)
			elif source == "Latest Purchase Rate":
				choices = [
					submitted(company, item, uom, currency, date, doctype, context, lock=lock)
					for doctype in ("Purchase Invoice", "Purchase Receipt")
				]
				available = [value for value in choices if value.get("cost_rate") is not None]
				result = (
					max(
						available,
						key=lambda row: (row["cost_date"], str(row["cost_created"]), row["source_document"]),
					)
					if available
					else {"cost_rate": None}
				)
			else:
				if source == "Supplier Latest Purchase Rate" and not context.get("supplier"):
					raise ValueError("Select a Supplier for Supplier Latest Purchase Rate")
				doctype = "Purchase Receipt" if "Receipt" in source else "Purchase Invoice"
				current = source.startswith("Current ")
				if current and (
					context.get("source_doctype") != doctype or not context.get("source_document")
				):
					raise ValueError("Select the current submitted " + doctype + " on the revision")
				result = submitted(
					company, item, uom, currency, date, doctype, context, current=current, lock=lock
				)
			attempts.append({"source": source, "reason": result.get("cost_reason")})
			if result.get("cost_rate") is not None:
				result.update(cost_source=source, cost_attempts=attempts)
				return result
		except ValueError as exc:
			attempts.append({"source": source, "reason": str(exc)})
	return {
		"cost_rate": None,
		"cost_reason": "; ".join(
			row["source"] + ": " + (row.get("reason") or "No permitted positive cost") for row in attempts
		),
		"cost_attempts": attempts,
	}


def submitted(company, item, uom, currency, date, doctype, context, *, current=False, lock=False):
	frappe.has_permission(doctype, "read", throw=True)
	filters = [
		[doctype, "company", "=", company],
		[doctype, "docstatus", "=", 1],
		[doctype, "is_return", "=", 0],
		[doctype, "posting_date", "<=", date],
		[doctype + " Item", "item_code", "=", item.name],
		[doctype + " Item", "stock_qty", ">", 0],
		[doctype + " Item", "base_net_amount", ">", 0],
	]
	if context.get("supplier"):
		filters.append([doctype, "supplier", "=", context["supplier"]])
	if current:
		filters.append([doctype, "name", "=", context["source_document"]])
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=["name"],
		distinct=True,
		order_by="posting_date desc, creation desc, name desc",
		limit_page_length=1,
	)
	if not rows:
		return {"cost_rate": None, "cost_reason": "No permitted submitted positive " + doctype}
	doc = frappe.get_doc(doctype, rows[0].name, for_update=lock)
	doc.check_permission("read")
	if (
		doc.company != company
		or doc.docstatus != 1
		or doc.is_return
		or getdate(doc.posting_date) > getdate(date)
		or (context.get("supplier") and doc.supplier != context["supplier"])
	):
		raise ValueError("Selected purchase source changed or no longer matches the pricing context")
	lines = [
		line
		for line in doc.items
		if line.item_code == item.name
		and number(line.stock_qty or 0) > 0
		and number(line.base_net_amount or 0) > 0
	]
	if not lines:
		raise ValueError("Purchase source no longer contains a usable cost")
	line = max(lines, key=lambda row: row.idx)
	base = frappe.get_cached_value("Company", company, "default_currency")
	fx, reference = repository.exchange_rate(base, currency, date, lock=lock)
	return {
		"cost_rate": float(
			number(line.base_net_amount) / number(line.stock_qty) * repository.uom_factor(item, uom) * fx
		),
		"supplier": doc.supplier,
		"source_doctype": doctype,
		"source_document": doc.name,
		"source_detail": line.name,
		"source_invoice": doc.name if doctype == "Purchase Invoice" else None,
		"source_invoice_item": line.name if doctype == "Purchase Invoice" else None,
		"cost_date": str(doc.posting_date),
		"cost_created": str(doc.creation),
		"cost_modified": str(doc.modified),
		"source_stock_qty": line.stock_qty,
		"source_base_net_amount": line.base_net_amount,
		"exchange_rate": float(fx),
		"exchange_reference": reference,
	}


def valuation(company, item, uom, currency, date, warehouse, *, lock=False):
	if not warehouse:
		raise ValueError("Valuation cost requires a specific Warehouse")
	frappe.has_permission("Stock Ledger Entry", "read", throw=True)
	rows = frappe.get_list(
		"Stock Ledger Entry",
		filters={
			"company": company,
			"warehouse": warehouse,
			"item_code": item.name,
			"is_cancelled": 0,
			"posting_datetime": ["<", add_days(date, 1)],
		},
		fields=["name"],
		order_by="posting_datetime desc, creation desc, name desc",
		limit_page_length=1,
	)
	if not rows:
		return {"cost_rate": None, "cost_reason": "No permitted stock ledger valuation at the effective date"}
	entry = frappe.get_doc("Stock Ledger Entry", rows[0].name, for_update=lock)
	entry.check_permission("read")
	if (
		entry.is_cancelled
		or entry.company != company
		or entry.warehouse != warehouse
		or entry.item_code != item.name
		or getdate(entry.posting_datetime) > getdate(date)
	):
		raise ValueError("Stock ledger evidence changed")
	if number(entry.valuation_rate or 0) <= 0:
		return {"cost_rate": None, "cost_reason": "Latest ledger valuation is not positive"}
	base = frappe.get_cached_value("Company", company, "default_currency")
	fx, reference = repository.exchange_rate(base, currency, date, lock=lock)
	return {
		"cost_rate": float(number(entry.valuation_rate) * repository.uom_factor(item, uom) * fx),
		"source_doctype": "Stock Ledger Entry",
		"source_document": entry.name,
		"source_detail": entry.voucher_detail_no,
		"cost_date": str(entry.posting_date),
		"cost_modified": str(entry.modified),
		"source_valuation_rate": entry.valuation_rate,
		"exchange_rate": float(fx),
		"exchange_reference": reference,
	}
