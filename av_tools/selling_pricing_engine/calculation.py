"""Deterministic pricing arithmetic, independent of Frappe and database state."""

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import pairwise

METHODS = ("Markup Percentage", "Target Gross Margin", "Fixed Addition", "Fixed Selling Price")
ROUNDING = {"Nearest": ROUND_HALF_UP, "Round Up": ROUND_CEILING, "Round Down": ROUND_FLOOR}


def number(value):
	try:
		result = Decimal(str(value))
	except (InvalidOperation, ValueError, TypeError) as exc:
		raise ValueError("A finite numeric value is required") from exc
	if not result.is_finite():
		raise ValueError("A finite numeric value is required")
	return result


def validate_method(method, value):
	if method not in METHODS:
		raise ValueError("Select a supported calculation method")
	value = number(value)
	if value < 0 or (method == "Target Gross Margin" and value >= 100):
		raise ValueError("Use a non-negative value and a target margin below 100%")
	if method == "Fixed Selling Price" and value <= 0:
		raise ValueError("Fixed selling prices must be greater than zero")
	return value


def margin(cost, selling):
	if cost is None:
		return None
	cost, selling = number(cost), number(selling)
	if selling <= 0:
		raise ValueError("Selling price must be greater than zero")
	return (selling - cost) * 100 / selling


def calculate(cost, method, value, rounding="No Rounding", increment=1, precision=6):
	value = validate_method(method, value)
	if method == "Fixed Selling Price":
		raw = value
	else:
		if cost is None or number(cost) <= 0:
			raise ValueError("A usable positive purchase cost is required")
		cost = number(cost)
		if method == "Markup Percentage":
			raw = cost * (1 + value / 100)
		elif method == "Target Gross Margin":
			raw = cost / (1 - value / 100)
		else:
			raw = cost + value
	if rounding != "No Rounding":
		if rounding not in ROUNDING or number(increment) <= 0:
			raise ValueError("Select a rounding method and positive increment")
		rounded = (raw / number(increment)).to_integral_value(rounding=ROUNDING[rounding]) * number(increment)
	else:
		rounded = raw
	if not 1 <= int(precision) <= 9:
		raise ValueError("Rate precision must be between 1 and 9")
	# Minimum margin must be checked AFTER both commercial and storage rounding.
	rounded = rounded.quantize(Decimal(1).scaleb(-int(precision)), rounding=ROUND_HALF_UP)
	if rounded <= 0:
		raise ValueError("Rounding produced a non-positive selling price")
	return raw, rounded


def rule_priority(rule):
	"""Documented Phase 2 tiers; warehouse scopes beat independent Branch scopes."""
	item, group, supplier = (
		bool(rule.get("item_code")),
		bool(rule.get("item_group")),
		bool(rule.get("supplier")),
	)
	warehouse, branch = bool(rule.get("warehouse")), bool(rule.get("branch"))
	if item:
		return (
			(100 if supplier else 90)
			if warehouse
			else (85 if supplier else 80)
			if branch
			else 70
			if supplier
			else 60
		)
	if group:
		return 50 if warehouse else 45 if branch else 40
	if supplier:
		return 35 if warehouse else 33 if branch else 30
	return 20 if warehouse else 10 if branch else 0


def matching_rules(
	rules, item_code, warehouse, uom, effective_date, *, supplier=None, branch=None, item_groups=()
):
	matches = []
	groups = list(item_groups)
	for rule in rules:
		if rule.get("disabled"):
			continue
		if any(
			rule.get(k) and rule[k] != v
			for k, v in (
				("item_code", item_code),
				("warehouse", warehouse),
				("uom", uom),
				("supplier", supplier),
				("branch", branch),
			)
		):
			continue
		group = rule.get("item_group")
		if group and (group not in groups or (group != groups[0] and not rule.get("include_child_groups"))):
			continue
		if str(rule.get("valid_from") or "0001-01-01") > str(effective_date):
			continue
		if str(rule.get("valid_upto") or "9999-12-31") < str(effective_date):
			continue
		rank = (rule_priority(rule), -groups.index(group) if group else 0, bool(rule.get("uom")))
		matches.append((rank, rule))
	matches.sort(key=lambda pair: pair[0], reverse=True)
	for (rank, first), (next_rank, second) in pairwise(matches):
		if rank == next_rank:
			raise ValueError(
				"Equally specific pricing rules conflict: " + first["name"] + ", " + second["name"]
			)
	return [rule for _rank, rule in matches]


def choose_rule(rules, item_code, warehouse, uom, effective_date, **context):
	matches = matching_rules(rules, item_code, warehouse, uom, effective_date, **context)
	return matches[0] if matches else None
