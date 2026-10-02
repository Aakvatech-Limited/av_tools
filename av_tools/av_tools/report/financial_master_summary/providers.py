# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.nestedset import get_descendants_of

from erpnext.accounts.report.asset_depreciations_and_balances import asset_depreciations_and_balances
from erpnext.accounts.report.general_ledger import general_ledger
from erpnext.stock.doctype.warehouse.warehouse import get_warehouses_based_on_account
from erpnext.stock.report.stock_balance import stock_balance


ASSET_ACCOUNT_FIELDS = {
	"Fixed Asset": "fixed_asset_account",
	"Accumulated Depreciation": "accumulated_depreciation_account",
	"Depreciation": "depreciation_expense_account",
}


def get_provider(account_type):
	if account_type == "Stock":
		return "Stock"
	if account_type in ASSET_ACCOUNT_FIELDS:
		return "Asset"
	return None


def get_master_summary(filters, account_type):
	provider = get_provider(account_type)
	if provider == "Stock":
		return get_stock_master_summary(filters)
	if provider == "Asset":
		return get_asset_master_summary(filters, account_type)
	frappe.throw(_("No non-party drill-down provider is configured for account type {0}.").format(account_type))


def get_stock_master_summary(filters):
	warehouses = get_warehouses_based_on_account(filters.account, filters.company)
	stock_filters = frappe._dict(
		company=filters.company,
		from_date=filters.from_date,
		to_date=filters.to_date,
		warehouse=warehouses,
	)
	_, stock_rows = stock_balance.execute(stock_filters)

	rows = []
	warehouse_totals = {}
	group_totals = {}
	item_totals = {}

	for source in stock_rows:
		warehouse = source.get("warehouse")
		item_group = source.get("item_group")
		item_code = source.get("item_code")
		if not warehouse or not item_code:
			continue

		_add_values(warehouse_totals.setdefault(warehouse, _empty_values()), source)
		group_key = (warehouse, item_group or _("Ungrouped"))
		_add_values(group_totals.setdefault(group_key, _empty_values()), source)
		item_key = (warehouse, item_group or _("Ungrouped"), item_code)
		_add_values(item_totals.setdefault(item_key, _empty_values()), source)

	for warehouse in sorted(warehouse_totals):
		values = warehouse_totals[warehouse]
		rows.append(
			_make_master_row(
				label=warehouse,
				master_type="Warehouse",
				master_value=warehouse,
				indent=0,
				values=values,
				warehouse=warehouse,
			)
		)

		groups = sorted(key for key in group_totals if key[0] == warehouse)
		for _, item_group in groups:
			values = group_totals[(warehouse, item_group)]
			rows.append(
				_make_master_row(
					label=item_group,
					master_type="Item Group",
					master_value=item_group,
					indent=1,
					values=values,
					warehouse=warehouse,
					item_group=item_group,
				)
			)

			items = sorted(
				key for key in item_totals if key[0] == warehouse and key[1] == item_group
			)
			for _, _, item_code in items:
				rows.append(
					_make_master_row(
						label=item_code,
						master_type="Item",
						master_value=item_code,
						indent=2,
						values=item_totals[(warehouse, item_group, item_code)],
						warehouse=warehouse,
						item_group=item_group,
						item=item_code,
					)
				)

	return _master_columns(), rows, _get_stock_reconciliation(filters, rows)


def get_asset_master_summary(filters, account_type):
	categories = get_asset_categories_for_account(filters.company, filters.account, account_type)
	if not categories:
		frappe.throw(_("No Asset Category is mapped to account {0}.").format(filters.account))

	report_filters = frappe._dict(
		company=filters.company,
		from_date=filters.from_date,
		to_date=filters.to_date,
		group_by="Asset",
		finance_book=filters.get("finance_book"),
	)
	_, asset_rows = asset_depreciations_and_balances.execute(report_filters)
	asset_names = [row.get("name") or row.get("asset") for row in asset_rows]
	asset_category_map = {
		row.name: row.asset_category
		for row in frappe.get_all(
			"Asset",
			filters={"name": ("in", [name for name in asset_names if name])},
			fields=["name", "asset_category"],
		)
	}

	rows = []
	for category in sorted(categories):
		category_assets = [
			row
			for row in asset_rows
			if asset_category_map.get(row.get("name") or row.get("asset")) == category
		]
		if not category_assets:
			continue

		category_values = _empty_values()
		for row in category_assets:
			_add_asset_values(category_values, row, account_type)

		rows.append(
			_make_master_row(
				label=category,
				master_type="Asset Category",
				master_value=category,
				indent=0,
				values=category_values,
				asset_category=category,
				provider="Asset",
			)
		)

		for source in sorted(category_assets, key=lambda row: row.get("name") or row.get("asset") or ""):
			asset = source.get("name") or source.get("asset")
			rows.append(
				_make_master_row(
					label=source.get("asset_name") or asset,
					master_type="Asset",
					master_value=asset,
					indent=1,
					values=_asset_values(source, account_type),
					asset_category=category,
					asset=asset,
					provider="Asset",
				)
			)

	return _master_columns(), rows, _get_asset_reconciliation(filters, rows, account_type)


def get_asset_categories_for_account(company, account, account_type):
	fieldname = ASSET_ACCOUNT_FIELDS.get(account_type)
	if not fieldname:
		return []

	filters = {"company_name": company, fieldname: account}
	categories = frappe.get_all("Asset Category Account", filters=filters, pluck="parent")

	if account_type == "Depreciation":
		default_account = frappe.get_cached_value("Company", company, "depreciation_expense_account")
		if default_account == account:
			categories += [
				row.parent
				for row in frappe.get_all(
					"Asset Category Account",
					filters={"company_name": company},
					fields=["parent", "depreciation_expense_account"],
				)
				if not row.depreciation_expense_account
			]

	return sorted(set(categories))


def get_stock_month_values(filters, period):
	warehouses = get_warehouses_based_on_account(filters.account, filters.company)
	if filters.get("warehouse"):
		warehouses = [warehouse for warehouse in warehouses if warehouse == filters.warehouse]

	stock_filters = frappe._dict(
		company=filters.company,
		from_date=period.from_date,
		to_date=period.to_date,
		warehouse=warehouses,
	)
	if filters.get("item"):
		stock_filters.item = [filters.item]
	elif filters.get("item_group"):
		stock_filters.item_group = filters.item_group

	_, rows = stock_balance.execute(stock_filters)
	values = _empty_values()
	for row in rows:
		_add_values(values, row)
	return values


def get_asset_month_values(filters, period, account_type):
	report_filters = frappe._dict(
		company=filters.company,
		from_date=period.from_date,
		to_date=period.to_date,
		group_by="Asset",
		finance_book=filters.get("finance_book"),
	)
	_, rows = asset_depreciations_and_balances.execute(report_filters)

	if filters.get("asset"):
		rows = [row for row in rows if (row.get("name") or row.get("asset")) == filters.asset]
	elif filters.get("asset_category"):
		names = [row.get("name") or row.get("asset") for row in rows]
		category_map = {
			row.name: row.asset_category
			for row in frappe.get_all(
				"Asset",
				filters={"name": ("in", [name for name in names if name])},
				fields=["name", "asset_category"],
			)
		}
		rows = [
			row
			for row in rows
			if category_map.get(row.get("name") or row.get("asset")) == filters.asset_category
		]

	values = _empty_values()
	for row in rows:
		_add_asset_values(values, row, account_type)
	return values


def get_stock_voucher_scope(filters):
	account = _single_account(filters.account)
	warehouses = get_warehouses_based_on_account(account, filters.company)
	if filters.get("warehouse"):
		warehouses = [warehouse for warehouse in warehouses if warehouse == filters.warehouse]

	sle_filters = {
		"company": filters.company,
		"is_cancelled": 0,
		"posting_date": ("between", [filters.from_date, filters.to_date]),
		"warehouse": ("in", warehouses),
	}

	if filters.get("item"):
		sle_filters["item_code"] = filters.item
	elif filters.get("item_group"):
		groups = [filters.item_group] + get_descendants_of("Item Group", filters.item_group)
		items = frappe.get_all("Item", filters={"item_group": ("in", groups)}, pluck="name")
		sle_filters["item_code"] = ("in", items or ["__no_item__"])

	return {
		(row.voucher_type, row.voucher_no)
		for row in frappe.get_all(
			"Stock Ledger Entry",
			filters=sle_filters,
			fields=["voucher_type", "voucher_no"],
		)
		if row.voucher_type and row.voucher_no
	}


def get_asset_voucher_scope(filters):
	account = _single_account(filters.account)
	asset_filters = {"company": filters.company, "docstatus": 1}
	if filters.get("asset"):
		asset_filters["name"] = filters.asset
	elif filters.get("asset_category"):
		asset_filters["asset_category"] = filters.asset_category

	assets = frappe.get_all(
		"Asset",
		filters=asset_filters,
		fields=["name", "purchase_invoice", "purchase_receipt", "journal_entry_for_scrap"],
	)
	asset_names = {row.name for row in assets}
	vouchers = set()

	for row in assets:
		if row.purchase_invoice:
			vouchers.add(("Purchase Invoice", row.purchase_invoice))
		if row.purchase_receipt:
			vouchers.add(("Purchase Receipt", row.purchase_receipt))
		if row.journal_entry_for_scrap:
			vouchers.add(("Journal Entry", row.journal_entry_for_scrap))

	if asset_names:
		for row in frappe.get_all(
			"GL Entry",
			filters={
				"company": filters.company,
				"account": account,
				"is_cancelled": 0,
				"posting_date": ("between", [filters.from_date, filters.to_date]),
				"against_voucher": ("in", list(asset_names)),
			},
			fields=["voucher_type", "voucher_no"],
		):
			if row.voucher_type and row.voucher_no:
				vouchers.add((row.voucher_type, row.voucher_no))

		for row in frappe.get_all(
			"Asset Repair",
			filters={
				"company": filters.company,
				"asset": ("in", list(asset_names)),
				"docstatus": 1,
				"completion_date": ("between", [filters.from_date, filters.to_date]),
			},
			fields=["name"],
		):
			vouchers.add(("Asset Repair", row.name))

		for row in frappe.get_all(
			"Asset Capitalization",
			filters={
				"company": filters.company,
				"target_asset": ("in", list(asset_names)),
				"docstatus": 1,
				"posting_date": ("between", [filters.from_date, filters.to_date]),
			},
			fields=["name"],
		):
			vouchers.add(("Asset Capitalization", row.name))

		sales_invoice_parents = frappe.get_all(
			"Sales Invoice Item",
			filters={"asset": ("in", list(asset_names)), "docstatus": 1},
			pluck="parent",
		)
		if sales_invoice_parents:
			for row in frappe.get_all(
				"Sales Invoice",
				filters={
					"name": ("in", sales_invoice_parents),
					"company": filters.company,
					"docstatus": 1,
					"posting_date": ("between", [filters.from_date, filters.to_date]),
				},
				fields=["name"],
			):
				vouchers.add(("Sales Invoice", row.name))

	return vouchers


def filter_general_ledger_by_vouchers(filters, voucher_scope):
	gl_filters = frappe._dict(filters.copy())
	gl_filters.provider = None
	gl_filters.master_type = None
	gl_filters.master_value = None
	gl_filters.warehouse = None
	gl_filters.item_group = None
	gl_filters.item = None
	gl_filters.asset_category = None
	gl_filters.asset = None
	gl_filters.account = [filters.account] if isinstance(filters.account, str) else filters.account
	if gl_filters.get("party") and isinstance(gl_filters.party, str):
		gl_filters.party = [gl_filters.party]
	gl_filters.categorize_by = ""
	gl_filters.setdefault("include_default_book_entries", 1)
	gl_filters.setdefault("include_dimensions", 1)

	columns, rows = general_ledger.execute(gl_filters)
	filtered = [
		row
		for row in rows
		if row.get("voucher_type")
		and row.get("voucher_no")
		and (row.get("voucher_type"), row.get("voucher_no")) in voucher_scope
	]
	return columns, filtered


def _master_columns():
	return [
		{"label": _("Master"), "fieldname": "master", "fieldtype": "Data", "width": 260},
		{"label": _("Master Type"), "fieldname": "master_type", "fieldtype": "Data", "width": 120},
		{"label": _("Opening Value"), "fieldname": "opening_value", "fieldtype": "Currency", "width": 140},
		{"label": _("Increase"), "fieldname": "increase_value", "fieldtype": "Currency", "width": 140},
		{"label": _("Decrease"), "fieldname": "decrease_value", "fieldtype": "Currency", "width": 140},
		{"label": _("Closing Value"), "fieldname": "closing_value", "fieldtype": "Currency", "width": 140},
	]


def _make_master_row(
	label,
	master_type,
	master_value,
	indent,
	values,
	warehouse=None,
	item_group=None,
	item=None,
	asset_category=None,
	asset=None,
	provider="Stock",
):
	return frappe._dict(
		master=label,
		master_type=master_type,
		master_value=master_value,
		provider=provider,
		indent=indent,
		warehouse=warehouse,
		item_group=item_group,
		item=item,
		asset_category=asset_category,
		asset=asset,
		**values,
	)


def _empty_values():
	return {
		"opening_value": 0.0,
		"increase_value": 0.0,
		"decrease_value": 0.0,
		"closing_value": 0.0,
	}


def _values_from_stock_row(row):
	return {
		"opening_value": flt(row.get("opening_val")),
		"increase_value": flt(row.get("in_val")),
		"decrease_value": flt(row.get("out_val")),
		"closing_value": flt(row.get("bal_val")),
	}


def _add_values(target, row):
	values = _values_from_stock_row(row)
	for fieldname in target:
		target[fieldname] += values[fieldname]


def _asset_values(row, account_type):
	if account_type == "Accumulated Depreciation":
		return {
			"opening_value": flt(row.get("accumulated_depreciation_as_on_from_date")),
			"increase_value": flt(row.get("depreciation_amount_during_the_period")),
			"decrease_value": flt(row.get("depreciation_eliminated_during_the_period"))
			+ flt(row.get("depreciation_eliminated_via_reversal")),
			"closing_value": flt(row.get("accumulated_depreciation_as_on_to_date")),
		}
	if account_type == "Depreciation":
		period_value = flt(row.get("depreciation_amount_during_the_period"))
		return {
			"opening_value": 0.0,
			"increase_value": period_value,
			"decrease_value": 0.0,
			"closing_value": period_value,
		}
	return {
		"opening_value": flt(row.get("value_as_on_from_date")),
		"increase_value": flt(row.get("value_of_new_purchase")) + flt(row.get("adjustment_during_period")),
		"decrease_value": flt(row.get("value_of_sold_asset"))
		+ flt(row.get("value_of_scrapped_asset"))
		+ flt(row.get("value_of_capitalized_asset")),
		"closing_value": flt(row.get("value_as_on_to_date")),
	}


def _add_asset_values(target, row, account_type):
	values = _asset_values(row, account_type)
	for fieldname in target:
		target[fieldname] += values[fieldname]


def _get_stock_reconciliation(filters, rows):
	stock_total = sum(row.closing_value for row in rows if row.indent == 0)
	gl_value = _get_gl_value(filters, balance=True)
	return _reconciliation_summary(stock_total, gl_value, _("Stock value"), _("GL closing"))


def _get_asset_reconciliation(filters, rows, account_type):
	provider_total = sum(row.closing_value for row in rows if row.indent == 0)
	gl_value = _get_gl_value(filters, balance=account_type != "Depreciation")
	if account_type == "Accumulated Depreciation":
		gl_value = abs(gl_value)
	return _reconciliation_summary(provider_total, gl_value, _("Asset provider"), _("GL value"))


def _get_gl_value(filters, balance=True):
	gl_filters = frappe._dict(filters.copy())
	gl_filters.account = [_single_account(filters.account)]
	gl_filters.presentation_currency = frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)
	gl_filters.categorize_by = ""
	gl_filters.setdefault("include_default_book_entries", 1)
	_, rows = general_ledger.execute(gl_filters)
	labels = general_ledger.get_translated_labels_for_totals()
	target = labels["closing"] if balance else labels["total"]
	row = next((row for row in rows if row.get("account") == target), frappe._dict())
	return flt(row.get("debit")) - flt(row.get("credit"))


def _single_account(account):
	if isinstance(account, list):
		if len(account) != 1:
			frappe.throw(_("Exactly one account is required for provider drill-down."))
		return account[0]
	return account


def _reconciliation_summary(provider_value, gl_value, provider_label, gl_label):
	difference = provider_value - gl_value
	indicator = "Green" if abs(difference) <= 0.1 else "Red"
	return [
		{"value": provider_value, "label": provider_label, "datatype": "Currency", "indicator": "Blue"},
		{"value": gl_value, "label": gl_label, "datatype": "Currency", "indicator": "Blue"},
		{"value": difference, "label": _("Difference"), "datatype": "Currency", "indicator": indicator},
	]
