"""Permission boundaries for the read-only financial queries."""

import frappe

CHILD_PARENTS = {
	"Depreciation Schedule": ("Asset Depreciation Schedule", "depreciation_schedule"),
	"Asset Category Account": ("Asset Category", "accounts"),
	"Asset Reconciliation Asset": ("Asset Capitalization Reconciliation", "assets"),
	"Asset Reconciliation Source": ("Asset Capitalization Reconciliation", "sources"),
	"Purchase Invoice Item": ("Purchase Invoice", "items"),
}

# Fail closed if a site moves any required accounting field to a higher permlevel.
READ_FIELDS = {
	"Asset": "asset_name asset_category total_asset_cost calculate_depreciation purchase_date available_for_use_date disposal_date status company journal_entry_for_scrap purchase_invoice purchase_invoice_item purchase_amount asset_quantity av_nta_purchase_invoice av_nta_purchase_invoice_item",
	"Asset Depreciation Schedule": "asset company",
	"Depreciation Schedule": "schedule_date depreciation_amount journal_entry",
	"GL Entry": "company posting_date is_cancelled voucher_no voucher_type account debit credit against_voucher",
	"Journal Entry": "company",
	"Asset Category": "",
	"Asset Category Account": "company_name fixed_asset_account",
	"Asset Capitalization Reconciliation": "company status",
	"Asset Reconciliation Asset": "asset allocated_amount",
	"Asset Reconciliation Source": "gl_entry source_voucher_type source_voucher source_line allocated_amount",
	"Purchase Invoice": "company",
	"Purchase Invoice Item": "expense_account base_net_amount qty",
}


def check_fields(doctype):
	parenttype = CHILD_PARENTS.get(doctype, (None,))[0]
	allowed = set(frappe.get_meta(doctype).get_permitted_fieldnames(parenttype=parenttype))
	if set(READ_FIELDS[doctype].split()) - allowed:
		frappe.throw(
			"You do not have permission to read all fields required for Asset reconciliation.",
			frappe.PermissionError,
		)


def permitted_names(doctype, cache):
	if doctype not in cache:
		# get_list applies role, user permission, owner, share and query conditions.
		frappe.has_permission(doctype, "read", throw=True)
		cache[doctype] = frappe.get_list(doctype, pluck="name", limit_page_length=0)
	return cache[doctype]


def run_permitted(query, doctype, cache):
	if ("fields", doctype) not in cache:
		check_fields(doctype)
		if doctype == "Asset Category":
			check_fields("Asset Category Account")
		cache[("fields", doctype)] = True
	table = frappe.qb.DocType(doctype)
	if doctype in CHILD_PARENTS:
		parenttype, parentfield = CHILD_PARENTS[doctype]
		names = permitted_names(parenttype, cache)
		query = query.where(table.parent.isin(names)).where(table.parenttype == parenttype)
		query = query.where(table.parentfield == parentfield)
	else:
		names = permitted_names(doctype, cache)
		query = query.where(table.name.isin(names))
	if not names:
		return []
	return query.run(as_dict=True)
