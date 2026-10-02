# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate

from erpnext.accounts.report.general_ledger import general_ledger


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate_filters(filters)

	gl_filters = _get_general_ledger_filters(filters)
	return general_ledger.execute(gl_filters)


def _validate_filters(filters):
	for fieldname in ("company", "account", "from_date", "to_date"):
		if not filters.get(fieldname):
			frappe.throw(_("{0} is required").format(frappe.unscrub(fieldname)))

	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be greater than To Date."))

	account = filters.account[0] if isinstance(filters.account, list) else filters.account
	account_doc = frappe.get_cached_value("Account", account, ["company", "is_group"], as_dict=True)
	if not account_doc:
		frappe.throw(_("Account {0} does not exist.").format(account))
	if account_doc.company != filters.company:
		frappe.throw(_("Account {0} does not belong to company {1}.").format(account, filters.company))


def _get_general_ledger_filters(filters):
	gl_filters = frappe._dict(filters.copy())

	if isinstance(gl_filters.account, str):
		gl_filters.account = [gl_filters.account]

	if gl_filters.get("party") and isinstance(gl_filters.party, str):
		gl_filters.party = [gl_filters.party]

	gl_filters.categorize_by = gl_filters.get("categorize_by") or "Categorize by Voucher (Consolidated)"
	gl_filters.setdefault("include_default_book_entries", 1)
	gl_filters.setdefault("include_dimensions", 1)

	return gl_filters
