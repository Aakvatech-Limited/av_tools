"""One calculation path for preview, publication rechecks and report proposals."""

import frappe

from av_tools.selling_pricing_engine import repository as store
from av_tools.selling_pricing_engine.access import check_context
from av_tools.selling_pricing_engine.calculation import calculate, choose_rule, margin, matching_rules, number


def effective_configuration(settings, policy, rule=None):
	config = {
		key: settings.get(key)
		for key in (
			"cost_basis",
			"calculation_method",
			"calculation_value",
			"rounding_method",
			"rounding_increment",
			"minimum_margin",
			"rate_precision",
		)
	}
	chain = rule if isinstance(rule, list) else [rule]
	for source in (policy, *reversed(chain)):
		if not source:
			continue
		if source.get("calculation_mode") == "Override":
			config.update({key: source.get(key) for key in ("calculation_method", "calculation_value")})
		if source.get("rounding_mode") == "Override":
			config.update({key: source.get(key) for key in ("rounding_method", "rounding_increment")})
		if source.get("cost_basis") not in (None, "", "Use Default"):
			config["cost_basis"] = source.get("cost_basis")
	return config


def calculate_row(settings, policy, context, *, fixed_input=None, lock=False):
	"""Return a complete audit row. Permission/configuration errors are not hidden."""
	company, price_list = settings.company, policy.price_list
	item_code, warehouse = context["item_code"], context.get("warehouse")
	date, end = str(context["valid_from"]), context.get("valid_upto")
	check_context(company, price_list, warehouse, item_code)
	item = store.item_for(item_code, date)
	uom = context.get("uom") or item.sales_uom or item.stock_uom
	store.uom_factor(item, uom)
	currency = frappe.get_cached_value("Price List", price_list, "currency")
	rules = store.rules_for(
		company, price_list, item_code=item_code, warehouse=warehouse, uom=uom, effective_date=date, lock=lock
	)
	expanded = settings.get("enable_phase_2")
	branch, chain = None, None
	if expanded:
		from av_tools.selling_pricing_engine.locations import branch_for
		from av_tools.selling_pricing_engine.policies import check_filters, groups

		check_filters(frappe._dict(context))
		branch = branch_for(company, warehouse, context.get("branch"))
		ancestry = groups(item.item_group)
		chain = matching_rules(
			rules,
			item_code,
			warehouse,
			uom,
			date,
			supplier=context.get("supplier"),
			branch=branch,
			item_groups=ancestry,
		)
		rule = chain[0] if chain else None
	else:
		rule = choose_rule(rules, item_code, warehouse, uom, date)
	config = effective_configuration(settings, policy, chain if expanded else rule)
	current_rows = store.price_rows(
		company,
		price_list,
		item_code,
		uom,
		warehouse,
		lock=lock,
		**({"branch": branch} if branch and not warehouse else {}),
	)
	current = store.valid_price(current_rows, date)
	if current and current.currency != currency:
		raise ValueError("Existing published price currency differs from the Price List")
	standard = store.standard_price(company, price_list, item, uom, date, lock=lock)
	old_rate = (
		(current.get("rate") if warehouse or branch else current.get("price_list_rate")) if current else None
	)
	existing_rate = old_rate if old_rate is not None else (standard.price_list_rate if standard else None)
	resolved_current = None
	if expanded and not current:
		from av_tools.selling_pricing_engine.locations import resolve

		resolved_current = resolve(company, price_list, item, uom, date, warehouse, branch)
		if resolved_current:
			existing_rate = resolved_current["rate"]
	try:
		if expanded:
			from av_tools.selling_pricing_engine.cost_sources import cost as get_cost

			basis = config.get("cost_basis") or "Latest Submitted Purchase Invoice"
			cost = get_cost(
				company,
				item,
				uom,
				currency,
				date,
				basis,
				context,
				fallbacks=settings.get("cost_fallbacks"),
				lock=lock,
			)
			supplier = context.get("supplier") or cost.get("supplier")
			chain = matching_rules(
				rules, item_code, warehouse, uom, date, supplier=supplier, branch=branch, item_groups=ancestry
			)
			rule = chain[0] if chain else None
			config = effective_configuration(settings, policy, chain)
			if config.get("cost_basis") and config["cost_basis"] != basis:
				cost = get_cost(
					company,
					item,
					uom,
					currency,
					date,
					config["cost_basis"],
					{**context, "supplier": supplier},
					fallbacks=settings.get("cost_fallbacks"),
					lock=lock,
				)
		else:
			cost = store.purchase_cost(company, item, uom, currency, date, lock=lock)
	except ValueError as exc:
		cost = {"cost_rate": None, "cost_reason": str(exc)}
	source, fallback = (
		"Calculated Rule"
		if rule
		else "Price List Default"
		if policy.calculation_mode == "Override"
		else "Company Default",
		None,
	)
	method, value = config["calculation_method"], config["calculation_value"]
	if fixed_input is not None:
		method, value, source = "Fixed Selling Price", fixed_input, "Imported Fixed Price"
	elif rule and config["calculation_method"] == "Fixed Selling Price":
		source = "Fixed Rule"
	if method != "Fixed Selling Price" and cost["cost_rate"] is None:
		if policy.fallback_price_list:
			fallback = store.standard_price(company, policy.fallback_price_list, item, uom, date, lock=lock)
		if fallback:
			method, value, source = "Fixed Selling Price", fallback.price_list_rate, "Base Price Fallback"
		elif standard and (warehouse or branch):
			method, value, source = "Fixed Selling Price", standard.price_list_rate, "Standard Price Fallback"
		else:
			raise ValueError(cost.get("cost_reason") or "No usable cost or fallback price")
	rounding = "No Rounding" if method == "Fixed Selling Price" else config["rounding_method"]
	raw, rounded = calculate(
		cost["cost_rate"], method, value, rounding, config["rounding_increment"], config["rate_precision"]
	)
	proposed = rounded
	if (
		settings.retain_price_decreases
		and source not in ("Fixed Rule", "Imported Fixed Price")
		and existing_rate is not None
		and number(existing_rate) > proposed
	):
		proposed, source = number(existing_rate), "Retained Current Price"
	new_margin = margin(cost["cost_rate"], proposed)
	old_margin = (
		margin(cost["cost_rate"], existing_rate) if existing_rate and cost["cost_rate"] is not None else None
	)
	status = (
		"Requires Review"
		if new_margin is None
		else "Blocked"
		if new_margin < number(config["minimum_margin"])
		else "Ready"
	)
	reason = (
		"Margin cannot be verified: explicit acknowledgement and review note required"
		if new_margin is None
		else "Below minimum margin after rounding"
		if status == "Blocked"
		else ""
	)
	# Reject future overlaps during preview, not halfway through a publication.
	conflicts = [row for row in current_rows if store.overlaps(row, date, end)]
	if len(conflicts) > 1 or any(row.valid_from and str(row.valid_from) > date for row in conflicts):
		status, reason = (
			"Blocked",
			"Price period overlaps a future or ambiguous existing price; set an explicit end date or resolve the overlap",
		)
	result = {
		"item_code": item_code,
		"warehouse": warehouse,
		"branch": branch,
		"uom": uom,
		"currency": currency,
		"valid_from": date,
		"valid_upto": end,
		"selected": 1,
		"fixed_input_rate": fixed_input,
		"cost_rate": cost["cost_rate"],
		"cost_available": int(cost["cost_rate"] is not None),
		"cost_source": cost.get("cost_source"),
		"source_invoice": cost.get("source_invoice"),
		"source_invoice_item": cost.get("source_invoice_item"),
		"supplier": cost.get("supplier") or context.get("supplier"),
		"source_doctype": cost.get("source_doctype")
		or ("Purchase Invoice" if cost.get("source_invoice") else None),
		"source_document": cost.get("source_document") or cost.get("source_invoice"),
		"source_detail": cost.get("source_detail") or cost.get("source_invoice_item"),
		"rule_tier": " + ".join(
			key.replace("_", " ").title()
			for key in ("item_code", "item_group", "supplier", "warehouse", "branch")
			if rule and rule.get(key)
		)
		or "Price List / Company",
		"exchange_rate": cost.get("exchange_rate"),
		"exchange_reference": cost.get("exchange_reference"),
		"pricing_rule": rule.get("name") if rule else None,
		"calculation_method": method,
		"calculation_value": value,
		"calculated_rate": float(raw),
		"rounded_rate": float(rounded),
		"proposed_rate": float(proposed),
		"previous_rate": float(existing_rate) if existing_rate is not None else None,
		"previous_margin": float(old_margin) if old_margin is not None else None,
		"proposed_margin": float(new_margin) if new_margin is not None else None,
		"minimum_margin": config["minimum_margin"],
		"price_source": source,
		"fallback_price_list": policy.fallback_price_list if fallback else None,
		"result": status,
		"exception_reason": reason,
	}
	snapshot = {
		"context": context,
		"fixed_input": fixed_input,
		"settings": settings.as_dict(),
		"policy": policy.as_dict(),
		"rules": rules,
		"cost": cost,
		"current": store.price_snapshot(current),
		"standard": store.price_snapshot(standard),
		"resolved_current": resolved_current,
		"overlaps": [store.price_snapshot(row) for row in conflicts],
		"fallback": store.price_snapshot(fallback),
		"result": result,
	}
	result["calculation_hash"] = store.digest(snapshot)
	result["calculation_snapshot"] = frappe.as_json(snapshot)
	return result
