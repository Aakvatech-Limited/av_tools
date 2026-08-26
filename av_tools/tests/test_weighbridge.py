# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from av_tools.weigh_bridge.api import (
	create_weighbridge_ticket,
	get_gateway_payload,
	get_reference_items,
	get_ticket_items,
	get_uom_conversion_factor,
	make_target_from_ticket,
	read_weight,
)
from av_tools.weigh_bridge.validation import validate_weighbridge_ticket

COMPANY = "_Test Company"
ITEM = "_Test Item"
WAREHOUSE = "_Test Warehouse - _TC"


def make_sales_order(qty=5, submit=False):
	from erpnext.selling.doctype.sales_order.test_sales_order import (
		make_sales_order as erpnext_make_sales_order,
	)

	return erpnext_make_sales_order(
		company=COMPANY,
		customer="_Test Customer",
		item_code=ITEM,
		qty=qty,
		rate=10,
		warehouse=WAREHOUSE,
		do_not_submit=not submit,
	)


class TestWeighbridgeSettings(IntegrationTestCase):
	def test_read_weight_requires_enabled_settings(self):
		settings = frappe.get_single("Weighbridge Settings")
		settings.enabled = 0
		settings.save()
		self.assertRaises(frappe.ValidationError, read_weight)
		settings.enabled = 1
		settings.read_weight_url = ""
		settings.save()
		self.assertRaises(frappe.ValidationError, get_gateway_payload)
		settings.read_weight_url = "http://scale.local/read"
		settings.timeout_seconds = 9
		settings.save()
		self.assertEqual(read_weight("tare"), {"read_weight_url": "http://scale.local/read", "mode": "tare"})
		self.assertEqual(get_gateway_payload()["timeout_seconds"], 9)

	def test_uom_conversion(self):
		self.assertEqual(get_uom_conversion_factor("Kg", "Kg"), {"conversion_factor": 1.0})
		self.assertRaises(frappe.ValidationError, get_uom_conversion_factor, "", "Kg")
		if frappe.db.exists("UOM Conversion Factor", {"from_uom": "Kg", "to_uom": "Gram"}):
			self.assertEqual(get_uom_conversion_factor("Kg", "Gram")["conversion_factor"], 1000)


class TestWeighbridgeTicketFlow(IntegrationTestCase):
	def test_reference_items_and_ticket_creation(self):
		so = make_sales_order()
		self.assertRaises(frappe.ValidationError, get_reference_items, "Sales Order", None)
		self.assertRaises(frappe.ValidationError, get_reference_items, "Journal Entry", so.name)
		reference = get_reference_items("Sales Order", so.name)
		self.assertEqual([r["item_code"] for r in reference["items"]], [ITEM])
		self.assertEqual(reference["customer"], "_Test Customer")

		ticket_name = create_weighbridge_ticket(so.name, "Sales Order")
		ticket = frappe.get_doc("Weighbridge Ticket", ticket_name)
		self.assertEqual(ticket.document_reference, so.name)
		self.assertEqual(ticket.customer, "_Test Customer")
		self.assertEqual(ticket.items[0].item_code, ITEM)
		self.assertRaises(frappe.ValidationError, create_weighbridge_ticket, "", "Sales Order")

	def test_submit_updates_draft_reference_quantities(self):
		so = make_sales_order(qty=5)
		ticket = frappe.get_doc("Weighbridge Ticket", create_weighbridge_ticket(so.name, "Sales Order"))
		ticket.items[0].qty = 7
		ticket.tare_weight = 1000
		ticket.gross_weight = 8000
		ticket.save()
		ticket.submit()
		so.reload()
		self.assertEqual(so.items[0].qty, 7)
		self.assertEqual(ticket.docstatus, 1)
		ticket.cancel()
		self.assertEqual(ticket.docstatus, 2)

	def test_target_mapping_rules(self):
		so = make_sales_order()
		ticket = frappe.get_doc("Weighbridge Ticket", create_weighbridge_ticket(so.name, "Sales Order"))
		ticket.target_document_type = "Sales Order"
		self.assertRaises(frappe.ValidationError, ticket.save)
		ticket.reload()
		ticket.target_document_type = "Purchase Invoice"
		self.assertRaises(frappe.ValidationError, ticket.save)
		ticket.reload()
		ticket.target_document_type = "Sales Invoice"
		ticket.save()
		ticket.items = []
		ticket.append("items", {"item_code": "_Test Item 2", "qty": 1})
		self.assertRaises(frappe.ValidationError, ticket.save)

	def test_ticket_items_and_target_creation(self):
		so = make_sales_order(qty=5, submit=True)
		ticket = frappe.get_doc("Weighbridge Ticket", create_weighbridge_ticket(so.name, "Sales Order"))
		ticket.items[0].qty = 5
		ticket.save()
		self.assertRaises(frappe.ValidationError, get_ticket_items, ticket.name)
		ticket.submit()

		self.assertRaises(frappe.ValidationError, get_ticket_items, "")
		items = get_ticket_items(ticket.name, "Sales Invoice")
		self.assertEqual(items["items"][0]["sales_order"], so.name)
		self.assertEqual(items["items"][0]["so_detail"], so.items[0].name)
		self.assertEqual(items["document_reference"], so.name)
		self.assertRaises(frappe.ValidationError, get_ticket_items, ticket.name, "Sales Order", "SO-OTHER")

		frappe.flags.args = {}
		self.assertRaises(frappe.ValidationError, make_target_from_ticket, ticket.name)
		frappe.flags.args = {"target_doctype": "Sales Invoice"}
		try:
			target = make_target_from_ticket(ticket.name)
		finally:
			frappe.flags.args = None
		self.assertEqual(target.doctype, "Sales Invoice")
		self.assertEqual(target.customer, "_Test Customer")
		self.assertEqual([(r.item_code, r.qty) for r in target.items], [(ITEM, 5)])
		self.assertTrue(target.debit_to)

	def test_document_validation_hook(self):
		so = make_sales_order(qty=5, submit=True)
		ticket = frappe.get_doc("Weighbridge Ticket", create_weighbridge_ticket(so.name, "Sales Order"))
		ticket.items[0].qty = 5
		ticket.save()

		invoice = frappe.new_doc("Sales Invoice")
		invoice.customer = "_Test Customer"
		invoice.company = COMPANY
		invoice.append("items", {"item_code": ITEM, "qty": 5})
		self.assertIsNone(validate_weighbridge_ticket(invoice))

		invoice.weighbridge_ticket = ticket.name
		self.assertRaises(frappe.ValidationError, validate_weighbridge_ticket, invoice)
		ticket.submit()
		self.assertIsNone(validate_weighbridge_ticket(invoice))

		invoice.items[0].qty = 4
		self.assertRaises(frappe.ValidationError, validate_weighbridge_ticket, invoice)
		invoice.items[0].qty = 5
		invoice.append("items", {"item_code": "_Test Item 2", "qty": 1})
		self.assertRaises(frappe.ValidationError, validate_weighbridge_ticket, invoice)

		other_order = frappe.new_doc("Sales Order")
		other_order.name = "SO-OTHER"
		other_order.weighbridge_ticket = ticket.name
		self.assertRaises(frappe.ValidationError, validate_weighbridge_ticket, other_order)
