"""Opt-in fiscal-year Existing Asset drafts for newly invoiced fixed assets."""

import hashlib
from decimal import ROUND_HALF_UP, Decimal

import frappe
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_dimensions
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.utils import cint, flt

SETTINGS = "AV Tools Settings"
METHODS = ("Straight Line", "Double Declining Balance", "Written Down Value")


def validate_settings(settings):
	if not settings.get("enable_no_time_appropriation_assets"):
		return
	if settings.get("nta_depreciation_method") not in METHODS:
		frappe.throw(_("Select an automatic depreciation method for no-time-appropriation Assets."))
	frequency = flt(settings.get("nta_depreciation_frequency"))
	duration = flt(settings.get("nta_depreciation_duration_years"))
	if frequency <= 0 or duration <= 0 or frequency != int(frequency) or duration != int(duration):
		frappe.throw(_("Depreciation frequency and duration must be positive whole numbers."))
	if (int(duration) * 12) % int(frequency):
		frappe.throw(_("Depreciation duration in months must be divisible by the frequency."))
	if (
		settings.nta_depreciation_method == "Written Down Value"
		and not 0 < flt(settings.get("nta_depreciation_rate")) <= 100
	):
		frappe.throw(
			_("Written Down Value requires a depreciation rate greater than 0 and no more than 100%.")
		)


def enabled():
	return cint(frappe.get_cached_value(SETTINGS, SETTINGS, "enable_no_time_appropriation_assets"))


class NoTimeAppropriationPurchaseInvoice:
	def process_fixed_asset(self):
		# Frappe v16 composes this mixin with the normal controller. Its native
		# auto-creation runs inside on_submit before doc_events, even with Item
		# auto_create_assets enabled. Suppress only that step when our feature owns it.
		if not self.get("is_return") and enabled():
			return
		return super().process_fixed_asset()


def unit_key(invoice, line, unit):
	return hashlib.sha256(f"{invoice}|{line}|{unit}".encode()).hexdigest()


def split_cost(total, count, precision=2):
	quantum = Decimal(1).scaleb(-precision)
	total = Decimal(str(total)).quantize(quantum, rounding=ROUND_HALF_UP)
	amount = (total / count).quantize(quantum, rounding=ROUND_HALF_UP)
	amounts = [amount] * (count - 1) + [total - amount * (count - 1)]
	if any(value <= 0 for value in amounts):
		frappe.throw(_("The invoice line cost must support a positive cost for every Asset."))
	return [float(value) for value in amounts]


def qualifying_rows(invoice):
	for row in invoice.get("items") or []:
		if not row.item_code:
			continue
		item = frappe.get_cached_doc("Item", row.item_code)
		if item.is_fixed_asset:
			if item.disabled or item.is_stock_item:
				frappe.throw(_("Row {0}: select an enabled, non-stock fixed asset Item.").format(row.idx))
			if not item.asset_category or not row.asset_location:
				frappe.throw(_("Row {0}: Asset Category and Asset Location are required.").format(row.idx))
			quantity = flt(row.qty)
			if quantity <= 0 or quantity != int(quantity) or flt(row.get("conversion_factor") or 1) != 1:
				frappe.throw(
					_("Row {0}: fixed assets require whole positive quantities in the stock UOM.").format(
						row.idx
					)
				)
			if row.get("wip_composite_asset"):
				frappe.throw(
					_("Row {0}: composite components need the standard capitalization process.").format(
						row.idx
					)
				)
			yield row, item, int(quantity)


def validate_purchase_invoice(doc, method=None):
	if doc.get("is_return") or not enabled():
		return
	rows = list(qualifying_rows(doc))
	if not rows:
		return
	settings = frappe.get_cached_doc(SETTINGS)
	validate_settings(settings)
	get_fiscal_year(doc.posting_date, company=doc.company, as_dict=True)
	for row, _item, count in rows:
		split_cost(line_cost(row, count), count, currency_precision())


def currency_precision():
	return cint(frappe.db.get_single_value("System Settings", "currency_precision") or 2)


def line_cost(row, count):
	# Same company-currency valuation basis used by BuyingController.make_asset.
	return flt(row.valuation_rate) * count if flt(row.valuation_rate) > 0 else flt(row.base_net_amount)


def check_existing_assets(invoice, row):
	# Privileged existence checks prevent duplicates even when an existing Asset
	# is hidden from this user. Do not reveal the hidden document's identity.
	if frappe.db.exists(
		"Asset", {"purchase_invoice": invoice.name, "purchase_invoice_item": row.name, "docstatus": ["!=", 2]}
	):
		frappe.throw(
			_(
				"Row {0}: Assets already exist against this invoice line; review them before proceeding."
			).format(row.idx)
		)
	if row.get("purchase_receipt"):
		filters = {
			"purchase_receipt": row.purchase_receipt,
			"item_code": row.item_code,
			"docstatus": ["!=", 2],
		}
		if row.get("pr_detail"):
			filters["purchase_receipt_item"] = ["in", [row.pr_detail, ""]]
		if frappe.db.exists("Asset", filters):
			frappe.throw(
				_(
					"Row {0}: the Purchase Receipt already has Assets. Review those Assets to avoid duplicate capitalization."
				).format(row.idx)
			)


def create_draft_assets(doc, method=None):
	if doc.docstatus != 1 or doc.get("is_return") or not enabled():
		return []
	rows = list(qualifying_rows(doc))
	if not rows:
		return []
	doc.check_permission("submit")
	frappe.has_permission("Asset", "create", throw=True)
	frappe.db.get_value("Purchase Invoice", doc.name, "name", for_update=True)
	settings = frappe.get_cached_doc(SETTINGS)
	validate_settings(settings)
	fiscal_year = get_fiscal_year(doc.posting_date, company=doc.company, as_dict=True)
	dimensions, defaults = get_dimensions(with_cost_center_and_project=True)
	created = []
	for row, item, count in rows:
		check_existing_assets(doc, row)
		amounts = split_cost(line_cost(row, count), count, currency_precision())
		for unit, amount in enumerate(amounts, start=1):
			key = unit_key(doc.name, row.name, unit)
			existing = frappe.db.get_value(
				"Asset", {"av_nta_unit_key": key}, ["name", "docstatus"], as_dict=True
			)
			if existing:
				if existing.docstatus == 2:
					frappe.throw(
						_(
							"Row {0}: a generated Asset was cancelled but not deleted. Review it before retrying."
						).format(row.idx)
					)
				continue
			depreciable = not frappe.get_cached_value(
				"Asset Category", item.asset_category, "non_depreciable_category"
			)
			asset = frappe.get_doc(
				{
					"doctype": "Asset",
					"asset_type": "Existing Asset",
					"docstatus": 0,
					"item_code": item.name,
					"asset_name": row.item_name or item.item_name,
					"naming_series": item.asset_naming_series or "ACC-ASS-.YYYY.-",
					"company": doc.company,
					"supplier": doc.supplier,
					"location": row.asset_location,
					"asset_owner": "Company",
					"asset_owner_company": doc.company,
					"asset_category": item.asset_category,
					"asset_quantity": 1,
					"purchase_date": fiscal_year.year_start_date,
					"available_for_use_date": fiscal_year.year_start_date,
					"net_purchase_amount": amount,
					"purchase_amount": amount,
					"calculate_depreciation": int(depreciable),
					"opening_accumulated_depreciation": 0,
					"opening_number_of_booked_depreciations": 0,
					"av_nta_purchase_invoice": doc.name,
					"av_nta_purchase_invoice_item": row.name,
					"av_nta_unit_number": unit,
					"av_nta_unit_key": key,
					"finance_books": [finance_book(settings, fiscal_year, doc.company)]
					if depreciable
					else [],
				}
			)
			for dimension in dimensions:
				field = dimension["fieldname"]
				asset.set(field, row.get(field) or doc.get(field) or defaults.get(doc.company, {}).get(field))
			# Normal insert checks permission, mandatory fields, category and costs;
			# ERPNext creates only draft schedules. No submit or GL posting here.
			asset.insert()
			created.append(asset.name)
	if created:
		frappe.msgprint(
			_("Created {0} draft Existing Assets for Finance review.").format(len(created)), alert=True
		)
	return created


def finance_book(settings, fiscal_year, company):
	return {
		"finance_book": settings.get("nta_finance_book")
		or frappe.get_cached_value("Company", company, "default_finance_book"),
		"depreciation_method": settings.nta_depreciation_method,
		"frequency_of_depreciation": cint(settings.nta_depreciation_frequency),
		"total_number_of_depreciations": cint(settings.nta_depreciation_duration_years)
		* 12
		// cint(settings.nta_depreciation_frequency),
		"depreciation_start_date": fiscal_year.year_end_date,
		"rate_of_depreciation": flt(settings.get("nta_depreciation_rate")),
		"daily_prorata_based": 0,
		"expected_value_after_useful_life": 0,
	}


def validate_asset_source(doc, method=None):
	old = doc.get_doc_before_save()
	fields = (
		"av_nta_purchase_invoice",
		"av_nta_purchase_invoice_item",
		"av_nta_unit_number",
		"av_nta_unit_key",
	)
	if old and old.get("av_nta_unit_key") and any(doc.get(field) != old.get(field) for field in fields):
		frappe.throw(
			_(
				"Generated Asset source references cannot be changed. Use the reviewed deletion action if needed."
			)
		)
	if not any(doc.get(field) for field in fields):
		return
	if not all(doc.get(field) for field in fields):
		frappe.throw(_("All generated Asset source references are required."))
	invoice = frappe.get_doc("Purchase Invoice", doc.av_nta_purchase_invoice)
	invoice.check_permission("read")
	line = next((row for row in invoice.items if row.name == doc.av_nta_purchase_invoice_item), None)
	unit = cint(doc.av_nta_unit_number)
	if (
		not line
		or invoice.docstatus != 1
		or invoice.is_return
		or invoice.company != doc.company
		or line.item_code != doc.item_code
		or not 1 <= unit <= flt(line.qty)
		or doc.asset_type != "Existing Asset"
		or doc.asset_quantity != 1
		or doc.av_nta_unit_key != unit_key(invoice.name, line.name, unit)
	):
		frappe.throw(_("Generated Asset source does not match a submitted Purchase Invoice line."))


def cancel_invoice_assets(doc, method=None):
	# Deliberately independent of the current setting: turning the feature off
	# must not strand Assets created when it was enabled.
	from av_tools.asset_reconciliation.asset_cleanup import build_plan, execute_plan

	assets = frappe.get_all("Asset", filters={"av_nta_purchase_invoice": doc.name}, pluck="name")
	plans = [build_plan(name) for name in assets]
	for plan in plans:
		if plan["blockers"]:
			frappe.throw(
				_("Cannot cancel invoice until linked Asset cleanup blockers are resolved: {0}").format(
					"; ".join(plan["blockers"])
				)
			)
	for plan in plans:
		execute_plan(plan)
