# Copyright (c) 2026, Aakvatech and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate


ANALYSIS_MODES = {
	"DocType Summary",
	"Document Candidates",
	"Field Changes",
	"Owner Summary",
}

CANDIDATE_FILTERS = {
	"All",
	"Orphan Version History",
	"Pre-Cutover Only",
	"Active Across Cutover",
	"Post-Cutover Only",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	version_rows = get_version_rows(filters)
	if not version_rows:
		return get_columns(filters.analysis_mode), []

	max_versions = int(filters.max_versions or 200000)
	if max_versions and len(version_rows) >= max_versions:
		frappe.msgprint(
			_(
				"The analysis reached the Max Versions limit of {0}. Narrow the filters or increase the limit for a complete result."
			).format(max_versions),
			indicator="orange",
		)

	if filters.analysis_mode == "Owner Summary":
		data = build_owner_summary(version_rows, filters)
		return get_columns(filters.analysis_mode), data

	document_map = build_document_map(version_rows, filters)

	if filters.analysis_mode == "Field Changes":
		data = build_field_changes(document_map)
		return get_columns(filters.analysis_mode), data

	existing_documents = get_existing_documents(document_map)

	if filters.analysis_mode == "Document Candidates":
		data = build_document_candidates(document_map, existing_documents, filters)
	else:
		data = build_doctype_summary(document_map, existing_documents)

	return get_columns(filters.analysis_mode), data


def validate_filters(filters):
	if not filters.cutover_date:
		frappe.throw(_("Operational Cutover Date is required."))

	if filters.analysis_mode not in ANALYSIS_MODES:
		frappe.throw(_("Invalid Analysis Mode."))

	candidate_filter = filters.candidate_filter or "All"
	if candidate_filter not in CANDIDATE_FILTERS:
		frappe.throw(_("Invalid Candidate Classification."))

	before_days = int(filters.before_days or 180)
	after_days = int(filters.after_days or 180)
	max_versions = int(filters.max_versions or 200000)

	if before_days < 0 or after_days < 0:
		frappe.throw(_("Days Before Cutover and Days After Cutover cannot be negative."))

	if max_versions <= 0:
		frappe.throw(_("Max Versions must be greater than zero."))

	filters.before_days = before_days
	filters.after_days = after_days
	filters.max_versions = max_versions
	filters.candidate_filter = candidate_filter


def get_version_rows(filters):
	cutover_datetime = get_datetime(filters.cutover_date)
	from_datetime = get_datetime(add_days(filters.cutover_date, -filters.before_days))
	to_datetime = get_datetime(add_days(filters.cutover_date, filters.after_days + 1))

	version_filters = [
		["Version", "creation", ">=", from_datetime],
		["Version", "creation", "<", to_datetime],
	]

	if filters.ref_doctype:
		version_filters.append(["Version", "ref_doctype", "=", filters.ref_doctype])

	if filters.owner:
		version_filters.append(["Version", "owner", "=", filters.owner])

	rows = frappe.get_all(
		"Version",
		filters=version_filters,
		fields=["name", "creation", "owner", "ref_doctype", "docname", "data"],
		order_by="creation asc",
		limit_page_length=filters.max_versions,
	)

	for row in rows:
		row["is_pre_cutover"] = row.creation < cutover_datetime

	return rows


def build_document_map(version_rows, filters):
	document_map = {}

	for row in version_rows:
		if not row.ref_doctype or not row.docname:
			continue

		key = (row.ref_doctype, row.docname)
		if key not in document_map:
			document_map[key] = {
				"ref_doctype": row.ref_doctype,
				"docname": row.docname,
				"version_count": 0,
				"pre_versions": 0,
				"post_versions": 0,
				"first_version": row.creation,
				"last_version": row.creation,
				"owners": set(),
				"data_import_versions": 0,
				"fields": defaultdict(int),
			}

		item = document_map[key]
		item["version_count"] += 1
		item["first_version"] = min(item["first_version"], row.creation)
		item["last_version"] = max(item["last_version"], row.creation)

		if row.owner:
			item["owners"].add(row.owner)

		if row.is_pre_cutover:
			item["pre_versions"] += 1
		else:
			item["post_versions"] += 1

		parsed_data = parse_version_data(row.data)
		if not parsed_data:
			continue

		if parsed_data.get("data_import"):
			item["data_import_versions"] += 1

		for change in parsed_data.get("changed") or []:
			if isinstance(change, (list, tuple)) and change:
				fieldname = change[0]
				if fieldname:
					item["fields"][fieldname] += 1

	return document_map


def parse_version_data(data):
	if not data:
		return {}

	try:
		parsed = frappe.parse_json(data)
		return parsed if isinstance(parsed, dict) else {}
	except Exception:
		return {}


def get_existing_documents(document_map):
	documents_by_doctype = defaultdict(list)
	for ref_doctype, docname in document_map:
		documents_by_doctype[ref_doctype].append(docname)

	existing_documents = {}

	for ref_doctype, names in documents_by_doctype.items():
		existing_documents[ref_doctype] = set()

		if not frappe.db.exists("DocType", ref_doctype):
			continue

		for start in range(0, len(names), 500):
			chunk = names[start : start + 500]
			try:
				existing = frappe.get_all(
					ref_doctype,
					filters={"name": ["in", chunk]},
					pluck="name",
					limit_page_length=0,
				)
				existing_documents[ref_doctype].update(existing)
			except Exception:
				# Some virtual/system doctypes cannot be queried like normal database tables.
				continue

	return existing_documents


def classify_document(item, existing_documents):
	ref_doctype = item["ref_doctype"]
	docname = item["docname"]
	exists = docname in existing_documents.get(ref_doctype, set())

	if not exists:
		return "Orphan Version History", False
	if item["pre_versions"] > 0 and item["post_versions"] == 0:
		return "Pre-Cutover Only", True
	if item["pre_versions"] > 0 and item["post_versions"] > 0:
		return "Active Across Cutover", True
	if item["pre_versions"] == 0 and item["post_versions"] > 0:
		return "Post-Cutover Only", True

	return "Unclassified", True


def build_doctype_summary(document_map, existing_documents):
	summary_map = {}

	for item in document_map.values():
		ref_doctype = item["ref_doctype"]
		if ref_doctype not in summary_map:
			summary_map[ref_doctype] = {
				"ref_doctype": ref_doctype,
				"document_count": 0,
				"version_count": 0,
				"pre_versions": 0,
				"post_versions": 0,
				"pre_only_documents": 0,
				"active_documents": 0,
				"post_only_documents": 0,
				"orphan_versions": 0,
				"orphan_documents": 0,
				"data_import_versions": 0,
			}

		summary = summary_map[ref_doctype]
		summary["document_count"] += 1
		summary["version_count"] += item["version_count"]
		summary["pre_versions"] += item["pre_versions"]
		summary["post_versions"] += item["post_versions"]
		summary["data_import_versions"] += item["data_import_versions"]

		classification, _exists = classify_document(item, existing_documents)
		if classification == "Orphan Version History":
			summary["orphan_documents"] += 1
			summary["orphan_versions"] += item["version_count"]
		elif classification == "Pre-Cutover Only":
			summary["pre_only_documents"] += 1
		elif classification == "Active Across Cutover":
			summary["active_documents"] += 1
		elif classification == "Post-Cutover Only":
			summary["post_only_documents"] += 1

	return sorted(summary_map.values(), key=lambda row: row["version_count"], reverse=True)


def build_document_candidates(document_map, existing_documents, filters):
	rows = []

	for item in document_map.values():
		classification, exists = classify_document(item, existing_documents)
		if filters.candidate_filter != "All" and classification != filters.candidate_filter:
			continue

		rows.append(
			{
				"ref_doctype": item["ref_doctype"],
				"docname": item["docname"],
				"exists": "Yes" if exists else "No",
				"classification": classification,
				"version_count": item["version_count"],
				"pre_versions": item["pre_versions"],
				"post_versions": item["post_versions"],
				"data_import_versions": item["data_import_versions"],
				"first_version": item["first_version"],
				"last_version": item["last_version"],
				"owners": ", ".join(sorted(item["owners"])),
			}
		)

	return sorted(rows, key=lambda row: row["version_count"], reverse=True)


def build_field_changes(document_map):
	field_map = {}

	for item in document_map.values():
		for fieldname, change_count in item["fields"].items():
			key = (item["ref_doctype"], fieldname)
			if key not in field_map:
				field_map[key] = {
					"ref_doctype": item["ref_doctype"],
					"fieldname": fieldname,
					"change_count": 0,
					"documents": set(),
				}

			field_map[key]["change_count"] += change_count
			field_map[key]["documents"].add(item["docname"])

	rows = []
	for item in field_map.values():
		rows.append(
			{
				"ref_doctype": item["ref_doctype"],
				"fieldname": item["fieldname"],
				"change_count": item["change_count"],
				"document_count": len(item["documents"]),
			}
		)

	return sorted(rows, key=lambda row: row["change_count"], reverse=True)


def build_owner_summary(version_rows, filters):
	owner_map = {}

	for row in version_rows:
		owner = row.owner or "Unknown"
		if owner not in owner_map:
			owner_map[owner] = {
				"owner": owner,
				"version_count": 0,
				"pre_versions": 0,
				"post_versions": 0,
				"doctypes": set(),
				"documents": set(),
				"first_activity": row.creation,
				"last_activity": row.creation,
			}

		item = owner_map[owner]
		item["version_count"] += 1
		item["first_activity"] = min(item["first_activity"], row.creation)
		item["last_activity"] = max(item["last_activity"], row.creation)

		if row.is_pre_cutover:
			item["pre_versions"] += 1
		else:
			item["post_versions"] += 1

		if row.ref_doctype:
			item["doctypes"].add(row.ref_doctype)
		if row.ref_doctype and row.docname:
			item["documents"].add((row.ref_doctype, row.docname))

	rows = []
	for item in owner_map.values():
		rows.append(
			{
				"owner": item["owner"],
				"version_count": item["version_count"],
				"pre_versions": item["pre_versions"],
				"post_versions": item["post_versions"],
				"doctype_count": len(item["doctypes"]),
				"document_count": len(item["documents"]),
				"first_activity": item["first_activity"],
				"last_activity": item["last_activity"],
			}
		)

	return sorted(rows, key=lambda row: row["version_count"], reverse=True)


def get_columns(analysis_mode):
	if analysis_mode == "Document Candidates":
		return [
			{"label": _("DocType"), "fieldname": "ref_doctype", "fieldtype": "Link", "options": "DocType", "width": 180},
			{"label": _("Document"), "fieldname": "docname", "fieldtype": "Dynamic Link", "options": "ref_doctype", "width": 220},
			{"label": _("Exists"), "fieldname": "exists", "fieldtype": "Data", "width": 70},
			{"label": _("Classification"), "fieldname": "classification", "fieldtype": "Data", "width": 190},
			{"label": _("Versions"), "fieldname": "version_count", "fieldtype": "Int", "width": 85},
			{"label": _("Pre"), "fieldname": "pre_versions", "fieldtype": "Int", "width": 70},
			{"label": _("Post"), "fieldname": "post_versions", "fieldtype": "Int", "width": 70},
			{"label": _("Data Import"), "fieldname": "data_import_versions", "fieldtype": "Int", "width": 95},
			{"label": _("First Version"), "fieldname": "first_version", "fieldtype": "Datetime", "width": 155},
			{"label": _("Last Version"), "fieldname": "last_version", "fieldtype": "Datetime", "width": 155},
			{"label": _("Owners"), "fieldname": "owners", "fieldtype": "Data", "width": 220},
		]

	if analysis_mode == "Field Changes":
		return [
			{"label": _("DocType"), "fieldname": "ref_doctype", "fieldtype": "Link", "options": "DocType", "width": 200},
			{"label": _("Field"), "fieldname": "fieldname", "fieldtype": "Data", "width": 220},
			{"label": _("Changes"), "fieldname": "change_count", "fieldtype": "Int", "width": 100},
			{"label": _("Documents"), "fieldname": "document_count", "fieldtype": "Int", "width": 100},
		]

	if analysis_mode == "Owner Summary":
		return [
			{"label": _("Owner"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 230},
			{"label": _("Versions"), "fieldname": "version_count", "fieldtype": "Int", "width": 100},
			{"label": _("Pre-Cutover"), "fieldname": "pre_versions", "fieldtype": "Int", "width": 110},
			{"label": _("Post-Cutover"), "fieldname": "post_versions", "fieldtype": "Int", "width": 110},
			{"label": _("DocTypes"), "fieldname": "doctype_count", "fieldtype": "Int", "width": 90},
			{"label": _("Documents"), "fieldname": "document_count", "fieldtype": "Int", "width": 100},
			{"label": _("First Activity"), "fieldname": "first_activity", "fieldtype": "Datetime", "width": 155},
			{"label": _("Last Activity"), "fieldname": "last_activity", "fieldtype": "Datetime", "width": 155},
		]

	return [
		{"label": _("DocType"), "fieldname": "ref_doctype", "fieldtype": "Link", "options": "DocType", "width": 200},
		{"label": _("Documents"), "fieldname": "document_count", "fieldtype": "Int", "width": 100},
		{"label": _("Versions"), "fieldname": "version_count", "fieldtype": "Int", "width": 100},
		{"label": _("Pre-Cutover Versions"), "fieldname": "pre_versions", "fieldtype": "Int", "width": 145},
		{"label": _("Post-Cutover Versions"), "fieldname": "post_versions", "fieldtype": "Int", "width": 150},
		{"label": _("Pre-Cutover Only Docs"), "fieldname": "pre_only_documents", "fieldtype": "Int", "width": 155},
		{"label": _("Across Cutover"), "fieldname": "active_documents", "fieldtype": "Int", "width": 120},
		{"label": _("Post-Cutover Only Docs"), "fieldname": "post_only_documents", "fieldtype": "Int", "width": 160},
		{"label": _("Orphan Versions"), "fieldname": "orphan_versions", "fieldtype": "Int", "width": 120},
		{"label": _("Orphan Documents"), "fieldname": "orphan_documents", "fieldtype": "Int", "width": 130},
		{"label": _("Data Import Versions"), "fieldname": "data_import_versions", "fieldtype": "Int", "width": 140},
	]
