import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def setup_custom_fields():
	custom_fields = {
		"Vehicle": [
			{
				"fieldname": "default_tare_weight",
				"label": "Default Tare Weight",
				"fieldtype": "Float",
				"insert_after": "license_plate",
			}
		],
	}

	item_doctypes = [
		"Sales Invoice Item",
		"Delivery Note Item",
		"Sales Order Item",
		"Purchase Order Item",
		"Purchase Invoice Item",
		"Purchase Receipt Item",
	]

	for dt in item_doctypes:
		custom_fields[dt] = [
			{
				"fieldname": "weighbridge_ticket",
				"label": "Weighbridge Ticket",
				"fieldtype": "Link",
				"options": "Weighbridge Ticket",
				"insert_after": "item_code",
				"read_only": 1,
			}
		]

	create_custom_fields(custom_fields, update=True)
