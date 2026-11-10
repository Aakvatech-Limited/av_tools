"""Reconstruct derived tax rows from transaction snapshots, without Frappe or writes."""

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

SOURCES = ("Sales Invoice", "Purchase Invoice")
DETAIL_FIELDS = ("item_row", "tax_row", "rate", "amount", "taxable_amount")


class CannotRebuild(ValueError):
	"""A posted source cannot be reconstructed without guessing."""


def number(value, label):
	try:
		result = Decimal(str(value))
	except (InvalidOperation, TypeError, ValueError) as exc:
		raise CannotRebuild(f"{label}: invalid number") from exc
	if not result.is_finite():
		raise CannotRebuild(f"{label}: non-finite number")
	return result


def fingerprint(source):
	"""Include all persisted source fields and current details to reject stale previews."""
	payload = {key: value for key, value in source.items() if not key.startswith("_")}
	return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def semantic_rows(rows):
	"""Ignore generated record IDs/order, but compare row links and stored amounts exactly."""
	result = []
	for row in rows:
		values = [str(row.get("item_row") or ""), str(row.get("tax_row") or "")]
		for field in ("rate", "amount", "taxable_amount"):
			try:
				value = number(row.get(field), field)
				# DECIMAL storage loses the sign of zero. Zero tax on a negative
				# exempt adjustment must compare equal to the database's positive 0.
				values.append("0" if value.is_zero() else str(value.normalize()))
			except CannotRebuild:
				values.append("invalid:" + str(row.get(field)))
		result.append(tuple(values))
	return sorted(result)


def reconstruct(source, precision=2, tolerance="0.5"):
	"""Only percentage-on-net taxes without invoice-level discounts are supported.

	Use saved per-item account rates (including explicit zero), never today's
	template. A saved tax-row rate is a fallback only for untemplated items.
	Reconcile every account independently, in base currency and with signed
	amounts; never proportionally scale a discrepancy to force a match.
	"""
	if source.get("doctype") not in SOURCES or source.get("docstatus") != 1:
		raise CannotRebuild("Select a submitted Sales Invoice or Purchase Invoice")
	if not isinstance(precision, int) or not 0 <= precision <= 6:
		raise CannotRebuild("Unsupported company currency precision")
	tolerance = number(tolerance, "Tolerance")
	if not 0 <= tolerance <= Decimal("0.5"):
		raise CannotRebuild("Rounding tolerance must be between 0 and 0.5 in base currency")
	for field in ("discount_amount", "base_discount_amount", "additional_discount_percentage"):
		if number(source.get(field) or 0, field):
			raise CannotRebuild("Invoice-level discounts require separate review")
	items, taxes = source.get("items") or [], source.get("taxes") or []
	if not items or not taxes:
		raise CannotRebuild("No invoice items or tax rows to reconstruct")
	for label, rows in (("item", items), ("tax", taxes)):
		ids = [row.get("name") for row in rows]
		if not all(ids) or len(ids) != len(set(ids)):
			raise CannotRebuild(f"Missing or duplicate source {label} row IDs")
	unit = Decimal(1).scaleb(-precision)
	proposed, controls = [], []
	for tax in taxes:
		label = f"Tax row {tax.get('idx')} ({tax.get('account_head')})"
		if tax.get("charge_type") != "On Net Total":
			raise CannotRebuild(f"{label}: unsupported charge type {tax.get('charge_type')}")
		if tax.get("is_tax_withholding_account"):
			raise CannotRebuild(f"{label}: withholding tax requires separate review")
		if tax.get("dont_recompute_tax"):
			raise CannotRebuild(f"{label}: manually frozen tax requires review")
		if not tax.get("account_head"):
			raise CannotRebuild(f"{label}: missing tax account")
		sign = Decimal(-1) if tax.get("add_deduct_tax") == "Deduct" else Decimal(1)
		expected = number(tax.get("base_tax_amount_after_discount_amount"), label) * sign
		if expected != expected.quantize(unit, rounding=ROUND_HALF_UP):
			raise CannotRebuild(f"{label}: posted tax has more decimals than the currency supports")
		rows = []
		for item in items:
			row_label = f"{label}, item row {item.get('idx')}"
			try:
				raw = item.get("item_tax_rate") or "{}"
				rates = json.loads(raw) if isinstance(raw, str) else raw
			except (ValueError, TypeError) as exc:
				raise CannotRebuild(f"{row_label}: invalid saved item tax rate JSON") from exc
			if not isinstance(rates, dict):
				raise CannotRebuild(f"{row_label}: saved tax rates must be a mapping")
			if tax["account_head"] in rates:
				rate = number(rates[tax["account_head"]], row_label)
			elif not item.get("item_tax_template"):
				rate = number(tax.get("rate"), row_label)
			else:
				raise CannotRebuild(
					f"{row_label}: template is linked but saved account-specific rate is missing"
				)
			base = number(item.get("base_net_amount"), row_label)
			amount = (base * rate / 100 * sign).quantize(unit, rounding=ROUND_HALF_UP)
			rows.append(
				{
					"item_row": item["name"],
					"tax_row": tax["name"],
					"rate": float(rate) if rate else 0.0,
					"amount": amount,
					"taxable_amount": float(base * sign) if base else 0.0,
				}
			)
		actual = sum((row["amount"] for row in rows), Decimal(0))
		difference = expected - actual
		if abs(difference) > tolerance:
			raise CannotRebuild(
				f"{label}: calculated {actual} vs posted {expected}; difference {difference} exceeds tolerance {tolerance}"
			)
		eligible = [row for row in rows if row["amount"] and row["rate"]]
		if difference:
			if not eligible:
				raise CannotRebuild(f"{label}: no taxable row for rounding adjustment")
			target = max(eligible, key=lambda row: abs(row["amount"]))
			adjusted = target["amount"] + difference
			if adjusted * target["amount"] < 0:
				raise CannotRebuild(f"{label}: rounding would reverse a row's tax sign")
			target["amount"] = adjusted
		for row in rows:
			row["amount"] = float(row["amount"]) if row["amount"] else 0.0
		controls.append(
			{
				"tax_row": tax["name"],
				"account": tax["account_head"],
				"posted": float(expected),
				"calculated": float(actual),
				"rounding": float(difference),
			}
		)
		proposed.extend(rows)
	return {
		"rows": proposed,
		"controls": controls,
		"changed": semantic_rows(proposed) != semantic_rows(source.get("item_wise_tax_details") or []),
	}
