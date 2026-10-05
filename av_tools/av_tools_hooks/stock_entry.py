import frappe
from frappe.utils import flt
from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict


def set_bom_guided_qty(doc, method=None):
	"""Store the BOM-prescribed quantity alongside the editable actual quantity."""
	if not doc.get("items"):
		return

	if not doc.get("bom_no") or not flt(doc.get("fg_completed_qty")):
		for row in doc.items:
			row.bom_guided_qty = None
		return

	raw_materials = get_bom_items_as_dict(
		doc.bom_no,
		doc.company,
		qty=doc.fg_completed_qty,
		fetch_exploded=doc.get("use_multi_level_bom"),
		fetch_qty_in_stock_uom=False,
	) or {}

	scrap_materials = get_bom_items_as_dict(
		doc.bom_no,
		doc.company,
		qty=doc.fg_completed_qty,
		fetch_exploded=0,
		fetch_scrap_items=1,
		fetch_qty_in_stock_uom=False,
	) or {}

	raw_qty = {item.item_code: flt(item.qty) for item in raw_materials.values()}
	scrap_qty = {item.item_code: flt(item.qty) for item in scrap_materials.values()}

	for row in doc.items:
		if row.get("is_finished_item"):
			row.bom_guided_qty = flt(doc.fg_completed_qty)
			continue

		lookup_item = row.get("original_item") or row.item_code
		if row.get("is_scrap_item"):
			row.bom_guided_qty = scrap_qty.get(lookup_item)
		else:
			row.bom_guided_qty = raw_qty.get(lookup_item)
