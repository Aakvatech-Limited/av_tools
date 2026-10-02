# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext.accounts.report.financial_statements import get_period_list
from erpnext.accounts.report.general_ledger import general_ledger

from av_tools.av_tools.report.financial_master_summary.providers import (
	get_asset_month_values,
	get_stock_month_values,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate_filters(filters)

	periods = get_period_list(
		None,
		None,
		getdate(filters.from_date),
		getdate(filters.to_date),
		"Date Range",
		"Monthly",
		company=filters.company,
		ignore_fiscal_year=True,
	)

	currency = _get_currency(filters)
	provider = filters.get("provider")

	if provider in ("Stock", "Asset"):
		account_type = frappe.get_cached_value("Account", filters.account, "account_type")
		rows = []
		for period in periods:
			if provider == "Stock":
				values = get_stock_month_values(filters, period)
			else:
				values = get_asset_month_values(filters, period, account_type)
			rows.append(_get_provider_month_row(period, values, currency))
		return _get_provider_columns(), rows

	rows = []
	for period in periods:
		gl_filters = _get_general_ledger_filters(filters, period)
		_, gl_data = general_ledger.execute(gl_filters)
		rows.append(_get_month_row(period, gl_data or [], currency))

	return _get_columns(), rows


def _validate_filters(filters):
	for fieldname in ("company", "account", "from_date", "to_date"):
		if not filters.get(fieldname):
			frappe.throw(_("{0} is required").format(frappe.unscrub(fieldname)))

	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be greater than To Date."))

	account = frappe.get_cached_value(
		"Account", filters.account, ["company", "is_group"], as_dict=True
	)
	if not account:
		frappe.throw(_("Account {0} does not exist.").format(filters.account))
	if account.company != filters.company:
		frappe.throw(_("Account {0} does not belong to company {1}.").format(filters.account, filters.company))
	if account.is_group:
		frappe.throw(_("Financial Monthly Summary requires a ledger account."))

	if filters.get("provider") not in ("Stock", "Asset"):
		for fieldname in ("party_type", "party"):
			if not filters.get(fieldname):
				frappe.throw(_("{0} is required").format(frappe.unscrub(fieldname)))
		if not frappe.db.exists(filters.party_type, filters.party):
			frappe.throw(_("Invalid {0}: {1}").format(filters.party_type, filters.party))


def _get_general_ledger_filters(filters, period):
	gl_filters = frappe._dict(filters.copy())
	gl_filters.from_date = period.from_date
	gl_filters.to_date = period.to_date
	gl_filters.account = [filters.account]
	gl_filters.party = [filters.party]
	gl_filters.categorize_by = ""
	gl_filters.setdefault("include_default_book_entries", 1)
	gl_filters.setdefault("include_dimensions", 0)
	return gl_filters


def _get_month_row(period, gl_data, currency):
	labels = general_ledger.get_translated_labels_for_totals()
	rows_by_label = {
		row.get("account"): row
		for row in gl_data
		if row.get("account") in labels.values()
	}
	opening = rows_by_label.get(labels["opening"], frappe._dict())
	total = rows_by_label.get(labels["total"], frappe._dict())
	closing = rows_by_label.get(labels["closing"], frappe._dict())

	return frappe._dict(
		{
			"month": period.label,
			"from_date": period.from_date,
			"to_date": period.to_date,
			"currency": currency,
			"opening_debit": flt(opening.get("debit")),
			"opening_credit": flt(opening.get("credit")),
			"debit": flt(total.get("debit")),
			"credit": flt(total.get("credit")),
			"closing_debit": flt(closing.get("debit")),
			"closing_credit": flt(closing.get("credit")),
		}
	)



def _get_provider_month_row(period, values, currency):
	return frappe._dict(
		month=period.label,
		from_date=period.from_date,
		to_date=period.to_date,
		currency=currency,
		opening_value=flt(values.get("opening_value")),
		increase_value=flt(values.get("increase_value")),
		decrease_value=flt(values.get("decrease_value")),
		closing_value=flt(values.get("closing_value")),
	)


def _get_provider_columns():
	return [
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Link", "width": 120},
		{"fieldname": "from_date", "label": _("From Date"), "fieldtype": "Date", "hidden": 1},
		{"fieldname": "to_date", "label": _("To Date"), "fieldtype": "Date", "hidden": 1},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
		{
			"fieldname": "opening_value",
			"label": _("Opening Value"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"fieldname": "increase_value",
			"label": _("Increase"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"fieldname": "decrease_value",
			"label": _("Decrease"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"fieldname": "closing_value",
			"label": _("Closing Value"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
	]


def _get_currency(filters):
	return (
		filters.get("presentation_currency")
		or frappe.get_cached_value("Account", filters.account, "account_currency")
		or frappe.get_cached_value("Company", filters.company, "default_currency")
	)


def _get_columns():
	return [
		{
			"fieldname": "month",
			"label": _("Month"),
			"fieldtype": "Link",
			"width": 120,
		},
		{
			"fieldname": "from_date",
			"label": _("From Date"),
			"fieldtype": "Date",
			"hidden": 1,
		},
		{
			"fieldname": "to_date",
			"label": _("To Date"),
			"fieldtype": "Date",
			"hidden": 1,
		},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
		{
			"fieldname": "opening_debit",
			"label": _("Opening (Dr)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "opening_credit",
			"label": _("Opening (Cr)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "debit",
			"label": _("Debit"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "credit",
			"label": _("Credit"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "closing_debit",
			"label": _("Closing (Dr)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "closing_credit",
			"label": _("Closing (Cr)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
	]
