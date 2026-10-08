import frappe
from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict
from frappe.utils import flt


def set_bom_guided_qty(doc, method=None):
	"""Capture the BOM baseline in transaction UOM and stock UOM without modifying actuals."""
	if not doc.get("items"):
		return

	if not doc.get("bom_no") or not flt(doc.get("fg_completed_qty")):
		for row in doc.items:
			row.bom_guided_qty = None
			row.bom_guided_stock_qty = None
		return

	def bom_quantities(**kwargs):
		items = get_bom_items_as_dict(
			doc.bom_no,
			doc.company,
			qty=doc.fg_completed_qty,
			fetch_qty_in_stock_uom=True,
			**kwargs,
		) or {}
		return {item.item_code: flt(item.qty) for item in items.values()}

	raw_qty = bom_quantities(fetch_exploded=doc.get("use_multi_level_bom"))
	scrap_qty = bom_quantities(fetch_exploded=0, fetch_scrap_items=1)

	for row in doc.items:
		factor = flt(row.get("conversion_factor"))
		if factor <= 0:
			frappe.throw(
				"Valid conversion factor required for BOM guidance on row {0} ({1})".format(
					row.idx, row.item_code
				)
			)

		if row.get("is_finished_item"):
			# Header finished quantity is expressed in the finished good's stock UOM.
			stock_guided = flt(doc.fg_completed_qty)
		else:
			lookup_item = row.get("original_item") or row.item_code
			quantities = scrap_qty if row.get("is_scrap_item") else raw_qty
			stock_guided = quantities.get(lookup_item, 0.0)

		row.bom_guided_stock_qty = stock_guided
		row.bom_guided_qty = stock_guided / factor
