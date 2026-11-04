"""Native Branch mapping and published Warehouse → Branch → standard resolution."""

import frappe
from frappe import _

from av_tools.selling_pricing_engine import repository
from av_tools.selling_pricing_engine.access import check_context, check_link


def branch_for(company, warehouse=None, branch=None):
	if warehouse:
		mapped = frappe.get_cached_value("Warehouse", warehouse, "custom_spe_branch")
		if branch and mapped != branch:
			frappe.throw(_("Warehouse does not belong to the selected Pricing Branch."))
		branch = mapped
	if branch:
		check_link("Branch", branch)
		if not frappe.db.exists(
			"Warehouse", {"company": company, "custom_spe_branch": branch, "disabled": 0}
		):
			frappe.throw(_("Map an enabled Warehouse in this Company to the selected Pricing Branch first."))
	return branch


def resolve(company, price_list, item, uom, date, warehouse=None, branch=None, *, alternate=True, seen=None):
	check_context(company, price_list, warehouse, item.name)
	branch = branch_for(company, warehouse, branch)
	seen = set(seen or ())
	if price_list in seen:
		raise ValueError("Cyclic runtime Price List fallback")
	seen.add(price_list)
	currency = frappe.get_cached_value("Price List", price_list, "currency")
	for scope, target in (("Warehouse", warehouse), ("Branch", branch)):
		if not target:
			continue
		kwargs = {"branch": branch} if scope == "Branch" else {}
		rows = repository.price_rows(
			company, price_list, item.name, uom, warehouse if scope == "Warehouse" else None, **kwargs
		)
		price = repository.valid_price(rows, date)
		if price:
			if price.currency != currency:
				raise ValueError("Published location price currency differs from its Price List")
			return {"rate": price.rate, "source": price.name, "price_list": price_list, "resolution": scope}
	standard = repository.standard_price(company, price_list, item, uom, date)
	if standard:
		return {
			"rate": standard.price_list_rate,
			"source": None,
			"price_list": price_list,
			"resolution": "Standard",
		}
	if alternate:
		# Sales reads must not require policy-management permissions or expose its cost fields.
		policy = frappe.db.get_value(
			"Selling Price List Policy",
			{"company": company, "price_list": price_list, "enabled": 1},
			["fallback_price_list", "runtime_fallback"],
			as_dict=True,
		)
		if policy and policy.runtime_fallback and policy.fallback_price_list:
			other = frappe.get_cached_doc("Price List", policy.fallback_price_list)
			owner = frappe.db.get_value("Selling Price List Policy", {"price_list": other.name}, "company")
			if (
				not other.enabled
				or not other.selling
				or other.currency != currency
				or (owner and owner != company)
			):
				raise ValueError(
					"Runtime fallback list must be enabled, selling, same-currency and not managed by another Company"
				)
			result = resolve(company, other.name, item, uom, date, warehouse, branch, seen=seen)
			if result:
				result["resolution"] = "Alternate List / " + result["resolution"]
			return result
	return None
