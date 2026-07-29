import frappe
from frappe.utils import cint


@frappe.whitelist(methods=["POST"])
def get_repack_template(template_name, qty):
	template_doc = frappe.get_doc("Repack Template", template_name)
	rows = [
		{
			"item_code": template_doc.item_code,
			"item_uom": template_doc.item_uom,
			"qty": cint(qty),
			"item_template": 1,
			"s_warehouse": template_doc.default_warehouse,
		}
	]

	for row in template_doc.repack_template_details:
		rows.append(
			{
				"item_code": row.item_code,
				"item_uom": row.item_uom,
				"qty": cint(float(row.qty / template_doc.qty) * float(qty)),
				"item_template": 0,
				"t_warehouse": row.default_target_warehouse,
			}
		)

	return rows
