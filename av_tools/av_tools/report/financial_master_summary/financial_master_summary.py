# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from erpnext.accounts.report.accounts_payable_summary.accounts_payable_summary import (
	execute as execute_payable_summary,
)
from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	execute as execute_receivable_summary,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate_filters(filters)

	account_type = frappe.get_cached_value("Account", filters.account, "account_type")
	filters.party_account = filters.account
	filters.report_date = filters.to_date
	filters.ageing_based_on = filters.get("ageing_based_on") or "Posting Date"
	filters.age_as_on = filters.get("age_as_on") or "Report Date"
	filters.range = filters.get("range") or "30, 60, 90, 120"

	if account_type == "Receivable":
		return execute_receivable_summary(filters)
	if account_type == "Payable":
		return execute_payable_summary(filters)

	frappe.throw(
		_("No master summary provider is configured yet for account type {0}.").format(
			account_type or _("Not Set")
		)
	)


def _validate_filters(filters):
	for fieldname in ("company", "account", "from_date", "to_date"):
		if not filters.get(fieldname):
			frappe.throw(_("{0} is required").format(frappe.unscrub(fieldname)))

	account = frappe.get_cached_value(
		"Account", filters.account, ["company", "is_group"], as_dict=True
	)
	if not account:
		frappe.throw(_("Account {0} does not exist.").format(filters.account))
	if account.company != filters.company:
		frappe.throw(_("Account {0} does not belong to company {1}.").format(filters.account, filters.company))
	if account.is_group:
		frappe.throw(_("Select a ledger account before opening the master summary."))
