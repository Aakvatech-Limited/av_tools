import frappe


def target_warehouse_based_price_list(doc, method):
	if not frappe.db.get_single_value("AV Tools Settings", "target_warehouse_based_price_list"):
		return

	for item in doc.items:
		if item.item_code is None or item.warehouse is None:
			frappe.throw(f"Both Item Code {item.item_code} and Warehouse {item.warehouse} are required.")

		price_list = frappe.db.get_value(
			"Dynamic Price List Assignment",
			{"supplier": doc.supplier, "warehouse": item.warehouse},
			"price_list",
		)
		if not price_list:
			frappe.throw(
				f"Price List not found. Please create one in Dynamic Price List Assignment for Supplier {doc.supplier} and Warehouse {item.warehouse}"
			)

		rate = frappe.db.get_value(
			"Item Price",
			{"item_code": item.item_code, "price_list": price_list},
			"price_list_rate",
		)
		if not rate:
			frappe.throw(f"Price List not found for Item {item.item_code}. Please create one.")

		item.price_list_rate = rate
		item.rate = rate
		item.amount = item.qty * rate
