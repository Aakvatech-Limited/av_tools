# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import glob
import json
import os

import frappe
from frappe.tests import IntegrationTestCase

APP = "av_tools"


class TestCustomizations(IntegrationTestCase):
	"""Custom fields, property setters and workspace links shipped by av_tools must exist on the site."""

	def json_custom_fields(self):
		folder = frappe.get_app_path(APP, "patches", "custom_fields", "custom_fields_json")
		for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
			with open(path) as handle:
				for field in json.load(handle):
					yield path, field

	def test_json_custom_fields_exist(self):
		checked = 0
		for path, field in self.json_custom_fields():
			if not frappe.db.exists("DocType", field["dt"]):
				continue
			with self.subTest(file=os.path.basename(path), field=f"{field['dt']}-{field['fieldname']}"):
				self.assertTrue(
					frappe.db.exists("Custom Field", {"dt": field["dt"], "fieldname": field["fieldname"]}),
					f"{field['dt']}-{field['fieldname']}",
				)
				checked += 1
		frappe.flags.av_tools_custom_fields_checked = checked
		self.assertGreater(checked, 10)

	def test_weighbridge_and_otp_custom_fields_exist(self):
		from av_tools.patches.custom_fields.auth_otp_custom_fields import execute as otp_fields
		from av_tools.weigh_bridge.custom_fields import setup_custom_fields

		setup_custom_fields()
		otp_fields()
		self.assertTrue(
			frappe.db.exists("Custom Field", {"dt": "Vehicle", "fieldname": "default_tare_weight"})
		)
		for doctype, fieldname in (
			("Sales Invoice", "authotp_validated"),
			("Customer", "is_authotp_applied"),
		):
			self.assertTrue(
				frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}),
				f"{doctype}-{fieldname}",
			)
		# weighbridge_ticket link fields were removed on purpose (patch remove_weighbridge_ticket_fields);
		# the link now lives on the ticket (document_reference / target_document_reference)
		self.assertFalse(
			frappe.get_all("Custom Field", filters={"fieldname": "weighbridge_ticket"}, pluck="dt")
		)
		meta = frappe.get_meta("Weighbridge Ticket")
		for fieldname in (
			"document_type",
			"document_reference",
			"target_document_type",
			"target_document_reference",
		):
			self.assertTrue(meta.has_field(fieldname), fieldname)

	def test_property_setters_exist(self):
		folder = frappe.get_app_path(APP, "patches", "property_setter", "property_setter_json")
		checked = 0
		for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
			with open(path) as handle:
				for setter in json.load(handle):
					if not frappe.db.exists("DocType", setter.get("doc_type")):
						continue
					with self.subTest(
						file=os.path.basename(path),
						setter=f"{setter['doc_type']}.{setter.get('field_name')}.{setter['property']}",
					):
						self.assertTrue(
							frappe.db.exists(
								"Property Setter",
								{
									"doc_type": setter["doc_type"],
									"field_name": setter.get("field_name"),
									"property": setter["property"],
								},
							)
						)
						checked += 1
		self.assertGreater(checked, 0)

	def test_workspace_links_resolve(self):
		path = frappe.get_app_path(APP, "workspace", "av_tools", "av_tools.json")
		with open(path) as handle:
			workspace = json.load(handle)
		self.assertTrue(frappe.db.exists("Workspace", workspace["name"]))
		checked = 0
		broken = []
		for link in workspace.get("links", []) + workspace.get("shortcuts", []):
			link_type = link.get("link_type") or link.get("type")
			target = link.get("link_to")
			if not target or link_type not in ("DocType", "Report", "Page"):
				continue
			checked += 1
			if not frappe.db.exists(link_type, target):
				broken.append(f"{link_type}: {target}")
		frappe.flags.av_tools_workspace_links = (checked, broken)
		self.assertFalse(broken, broken)
		self.assertGreater(checked, 10)

	def test_workspace_sidebar_json_valid(self):
		path = frappe.get_app_path(APP, "workspace_sidebar", "av_tools.json")
		with open(path) as handle:
			sidebar = json.load(handle)
		self.assertTrue(sidebar)

	def test_web_form_is_published_and_served(self):
		import requests

		self.assertTrue(frappe.db.exists("Web Form", "training-feedback-form"))
		route = frappe.db.get_value("Web Form", "training-feedback-form", "route")
		self.assertEqual(route, "feedback-form")
		port = frappe.get_conf().webserver_port or 8000
		try:
			response = requests.get(f"http://{frappe.local.site}:{port}/{route}", timeout=20)
		except requests.RequestException:
			self.skipTest("dev web server not reachable")
		self.assertEqual(response.status_code, 200)
		self.assertIn("web-form", response.text)

	def test_pages_registered(self):
		for page in ("salary-calculator", "user_manager"):
			with self.subTest(page=page):
				self.assertTrue(frappe.db.exists("Page", page), page)
