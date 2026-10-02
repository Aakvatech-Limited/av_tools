# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


_PLACEHOLDER = re.compile(r"^\{(ctx|row)\.([A-Za-z0-9_]+)(\?)?\}$")
_INLINE_PLACEHOLDER = re.compile(r"\{(ctx|row)\.([A-Za-z0-9_]+)(\?)?\}")
_OMIT = object()


class FinancialDrilldownRule(Document):
	def validate(self):
		try:
			template = frappe.parse_json(self.base_filter_template or "{}")
		except Exception as exc:
			frappe.throw(_("Base Filter Template must be valid JSON: {0}").format(exc))

		if not isinstance(template, dict):
			frappe.throw(_("Base Filter Template must be a JSON object."))


def _context_value(token, context):
	match = _PLACEHOLDER.match(token)
	if not match:
		return None, False, False

	source, fieldname, optional = match.groups()
	value = context.get(source, {}).get(fieldname)
	return value, True, bool(optional)


def _resolve_value(value, context):
	if isinstance(value, dict):
		if set(value) == {"$coalesce"}:
			for candidate in value["$coalesce"]:
				resolved = _resolve_value(candidate, context)
				if resolved is not _OMIT and resolved not in (None, "", [], {}):
					return resolved
			return _OMIT

		resolved_dict = {}
		for key, item in value.items():
			resolved = _resolve_value(item, context)
			if resolved is not _OMIT:
				resolved_dict[key] = resolved
		return resolved_dict

	if isinstance(value, list):
		resolved_list = []
		for item in value:
			resolved = _resolve_value(item, context)
			if resolved is not _OMIT:
				resolved_list.append(resolved)
		return resolved_list

	if not isinstance(value, str):
		return value

	resolved, is_placeholder, optional = _context_value(value, context)
	if is_placeholder:
		if resolved in (None, "", [], {}) and optional:
			return _OMIT
		if resolved is None:
			frappe.throw(_("Missing required drill-down filter value for {0}").format(value))
		return resolved

	def replace(match):
		source, fieldname, optional_marker = match.groups()
		resolved_value = context.get(source, {}).get(fieldname)
		if resolved_value in (None, ""):
			if optional_marker:
				return ""
			frappe.throw(
				_("Missing required drill-down filter value for {0}.{1}").format(source, fieldname)
			)
		return str(resolved_value)

	return _INLINE_PLACEHOLDER.sub(replace, value)


def resolve_filter_template(template, report_context, row_context):
	if isinstance(template, str):
		template = frappe.parse_json(template or "{}")
	if not isinstance(template, dict):
		frappe.throw(_("Base Filter Template must be a JSON object."))

	return _resolve_value(template, {"ctx": report_context or {}, "row": row_context or {}})


def _get_account_details(row_context):
	account = row_context.get("account")
	if not account:
		return

	if row_context.get("account_type") and row_context.get("root_type"):
		return

	details = frappe.get_cached_value("Account", account, ["account_type", "root_type"], as_dict=True)
	if not details:
		return

	row_context.setdefault("account_type", details.account_type)
	row_context.setdefault("root_type", details.root_type)


def _matches(rule, report_context, row_context, source_report):
	if rule.company and rule.company != report_context.get("company"):
		return False
	if rule.source_report and rule.source_report != source_report:
		return False
	if rule.account and rule.account != row_context.get("account"):
		return False
	if rule.account_type and rule.account_type != row_context.get("account_type"):
		return False
	if rule.root_type and rule.root_type != row_context.get("root_type"):
		return False
	return True


def _specificity(rule):
	return (
		1 if rule.account else 0,
		1 if rule.account_type else 0,
		1 if rule.root_type else 0,
		1 if rule.company else 0,
		1 if rule.source_report else 0,
		rule.priority or 0,
	)


def get_matching_rule(report_context, row_context, source_report=None):
	_get_account_details(row_context)

	rules = frappe.get_all(
		"Financial Drilldown Rule",
		filters={"enabled": 1},
		fields=[
			"name",
			"company",
			"source_report",
			"account",
			"account_type",
			"root_type",
			"target_report",
			"base_filter_template",
			"priority",
		],
	)

	matched = [rule for rule in rules if _matches(rule, report_context, row_context, source_report)]
	if not matched:
		return None

	return max(matched, key=_specificity)


@frappe.whitelist()
def get_drilldown_route(row_context=None, report_context=None, source_report=None):
	row_context = frappe.parse_json(row_context) or {}
	report_context = frappe.parse_json(report_context) or {}

	if not isinstance(row_context, dict) or not isinstance(report_context, dict):
		frappe.throw(_("Drill-down context must be JSON objects."))

	rule = get_matching_rule(report_context, row_context, source_report)
	if not rule:
		return {"matched": False}

	resolved_filters = resolve_filter_template(
		rule.base_filter_template,
		report_context,
		row_context,
	)

	return {
		"matched": True,
		"rule": rule.name,
		"target_report": rule.target_report,
		"route_options": resolved_filters,
	}
