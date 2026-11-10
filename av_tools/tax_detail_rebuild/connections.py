"""Native invoice Connections through typed links on rebuild result rows."""

from copy import deepcopy

TARGET = "Item Wise Tax Detail Rebuild"
ENTRY = "Item Wise Tax Detail Rebuild Entry"
LINK_FIELDS = {
	"Sales Invoice": "rebuild_sales_invoice",
	"Purchase Invoice": "rebuild_purchase_invoice",
}


def reference_fields(source_doctype, source_invoice):
	"""Keep the two Link columns mutually exclusive, including during backfill."""
	values = {fieldname: None for fieldname in LINK_FIELDS.values()}
	if source_doctype in LINK_FIELDS:
		values[LINK_FIELDS[source_doctype]] = source_invoice or None
	return values


def extend(data, source_doctype):
	data = deepcopy(data or {})
	transactions = data.setdefault("transactions", [])
	if not any(TARGET in group.get("items", []) for group in transactions):
		transactions.append({"label": "Tax Detail Maintenance", "items": [TARGET]})
	# This field exists only on the child table, unlike the optional source_invoice
	# field on the request parent. Frappe resolves its join and counts distinct parents.
	fieldname = LINK_FIELDS[source_doctype]
	data.setdefault("non_standard_fieldnames", {})[TARGET] = fieldname
	for group in transactions:
		if TARGET in group.get("items", []):
			group.setdefault("fieldnames", {})[TARGET] = fieldname
	return data


def sales_invoice(data):
	return extend(data, "Sales Invoice")


def purchase_invoice(data):
	return extend(data, "Purchase Invoice")
