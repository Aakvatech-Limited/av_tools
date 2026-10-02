# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _

import erpnext
from erpnext.accounts.report.trial_balance import trial_balance
from erpnext.accounts.utils import get_fiscal_year
from frappe.utils import add_days, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate_filters(filters)
	_set_trial_balance_defaults(filters)

	allowed_accounts = set(_get_leaf_accounts(filters.account, filters.company))
	columns, rows = _get_trial_balance_rows(filters, allowed_accounts)

	currency = filters.presentation_currency or erpnext.get_company_currency(filters.company)
	total_row = trial_balance.calculate_total_row(rows, currency, show_group_accounts=False)

	return columns, rows + ([{}, total_row] if rows else [])


def _validate_filters(filters):
	for fieldname in ("company", "account", "from_date", "to_date"):
		if not filters.get(fieldname):
			frappe.throw(_("{0} is required").format(frappe.unscrub(fieldname)))

	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be greater than To Date."))

	account_company = frappe.get_cached_value("Account", filters.account, "company")
	if account_company != filters.company:
		frappe.throw(_("Account {0} does not belong to company {1}.").format(filters.account, filters.company))


def _set_trial_balance_defaults(filters):
	filters.setdefault("show_group_accounts", 0)
	filters.setdefault("show_net_values", 1)
	filters.setdefault("include_default_book_entries", 1)
	filters.setdefault("with_period_closing_entry_for_opening", 1)
	filters.setdefault("with_period_closing_entry_for_current_period", 1)


def _get_trial_balance_rows(filters, allowed_accounts):
	columns = None
	merged = {}
	current_date = getdate(filters.from_date)
	to_date = getdate(filters.to_date)

	while current_date <= to_date:
		fiscal_year, year_start_date, year_end_date = get_fiscal_year(
			current_date, company=filters.company
		)
		segment_end = min(getdate(year_end_date), to_date)
		segment_filters = frappe._dict(filters.copy())
		segment_filters.fiscal_year = fiscal_year
		segment_filters.from_date = current_date
		segment_filters.to_date = segment_end

		segment_columns, segment_data = trial_balance.execute(segment_filters)
		columns = columns or segment_columns
		_merge_segment_rows(merged, segment_data or [], allowed_accounts)

		current_date = add_days(segment_end, 1)

	rows = list(merged.values())
	for row in rows:
		row.parent_account = ""
		row.indent = 0

	return columns or trial_balance.get_columns(), rows


def _merge_segment_rows(merged, segment_data, allowed_accounts):
	for row in segment_data:
		account = row.get("account")
		if account not in allowed_accounts:
			continue

		if account not in merged:
			merged[account] = frappe._dict(row.copy())
			continue

		target = merged[account]
		target.debit += row.get("debit", 0)
		target.credit += row.get("credit", 0)
		target.closing_debit = row.get("closing_debit", 0)
		target.closing_credit = row.get("closing_credit", 0)
		target.has_value = target.get("has_value") or row.get("has_value")


def _get_leaf_accounts(account, company):
	lft, rgt, is_group = frappe.get_cached_value(
		"Account", account, ["lft", "rgt", "is_group"]
	)

	if not is_group:
		return [account]

	return frappe.get_all(
		"Account",
		filters={
			"company": company,
			"is_group": 0,
			"lft": (">=", lft),
			"rgt": ("<=", rgt),
		},
		order_by="lft",
		pluck="name",
	)
