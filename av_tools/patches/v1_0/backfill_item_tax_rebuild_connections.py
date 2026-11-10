"""Backfill derived invoice Links on existing rebuild result rows after schema sync."""

import frappe

from av_tools.tax_detail_rebuild.connections import ENTRY, LINK_FIELDS, TARGET, reference_fields


def execute():
	if not frappe.db.exists("DocType", ENTRY):
		return
	parent_types = {}
	for row in frappe.get_all(
		ENTRY,
		filters={"parenttype": TARGET, "parentfield": "entries"},
		fields=["name", "parent", "source_doctype", "source_invoice", *LINK_FIELDS.values()],
		limit_page_length=0,
	):
		source_doctype = row.source_doctype
		if not source_doctype:
			if row.parent not in parent_types:
				parent_types[row.parent] = frappe.db.get_value(TARGET, row.parent, "source_doctype")
			source_doctype = parent_types[row.parent]
		values = reference_fields(source_doctype, row.source_invoice)
		if any(row.get(fieldname) != value for fieldname, value in values.items()):
			frappe.db.set_value(ENTRY, row.name, values, update_modified=False)
	for doctype in LINK_FIELDS:
		frappe.clear_cache(doctype=doctype)
