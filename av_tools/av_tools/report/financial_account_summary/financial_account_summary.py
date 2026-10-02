# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _

import erpnext
from erpnext.accounts.report.trial_balance import trial_balance
from erpnext.accounts.utils import get_fiscal_year


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate_filters(filters)
	_set_trial_balance_defaults(filters)

	columns, data = trial_balance.execute(filters)
	allowed_accounts = set(_get_leaf_accounts(filters.account, filters.company))
	rows = [row for row in (data or []) if row.get("account") in allowed_accounts]

	for row in rows:
		row.parent_account = ""
		row.indent = 0

	currency = filters.presentation_currency or erpnext.get_company_currency(filters.company)
	total_row = trial_balance.calculate_total_row(rows, currency, show_group_accounts=False)

	return columns, rows + ([{}, total_row] if rows else [])


def _validate_filters(filters):
	for fieldname in ("company", "account", "from_date", "to_date"):
		if not filters.get(fieldname):
			frappe.throw(_("{0} is required").format(frappe.unscrub(fieldname)))

	account_company = frappe.get_cached_value("Account", filters.account, "company")
	if account_company != filters.company:
		frappe.throw(_("Account {0} does not belong to company {1}.").format(filters.account, filters.company))


def _set_trial_balance_defaults(filters):
	if not filters.get("fiscal_year"):
		filters.fiscal_year = get_fiscal_year(filters.to_date, company=filters.company)[0]

	filters.setdefault("show_group_accounts", 0)
	filters.setdefault("show_net_values", 1)
	filters.setdefault("include_default_book_entries", 1)
	filters.setdefault("with_period_closing_entry_for_opening", 1)
	filters.setdefault("with_period_closing_entry_for_current_period", 1)


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
