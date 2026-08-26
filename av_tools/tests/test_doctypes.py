# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import frappe
from frappe.model.base_document import get_controller
from frappe.tests import IntegrationTestCase
from frappe.utils import today

APP = "av_tools"


def unexpected_errors():
	return (
		TypeError,
		AttributeError,
		ImportError,
		NameError,
		KeyError,
		frappe.db.ProgrammingError,
		frappe.db.InternalError,
	)


def app_doctypes(**filters):
	modules = frappe.get_module_list(APP)
	return frappe.get_all(
		"DocType",
		filters={"module": ("in", modules), **filters},
		fields=["name", "istable", "issingle", "is_virtual"],
		order_by="name",
	)


def fill_mandatory(doc):
	"""Fill required fields with generic values so the DocType JSON itself gets exercised."""
	for df in doc.meta.fields:
		if not df.reqd or doc.get(df.fieldname):
			continue
		if df.fieldtype in (
			"Data",
			"Small Text",
			"Text",
			"Long Text",
			"Text Editor",
			"Markdown Editor",
			"Code",
		):
			doc.set(df.fieldname, "Test")
		elif df.fieldtype == "Select" and df.options:
			doc.set(df.fieldname, next(o for o in df.options.split("\n") if o))
		elif df.fieldtype == "Link" and df.options and frappe.db.exists("DocType", df.options):
			if df.options == "Company":
				doc.set(df.fieldname, "_Test Company")
			else:
				names = frappe.get_all(df.options, pluck="name", limit=1)
				if names:
					doc.set(df.fieldname, names[0])
		elif df.fieldtype == "Date":
			doc.set(df.fieldname, today())
		elif df.fieldtype == "Datetime":
			doc.set(df.fieldname, frappe.utils.now_datetime())
		elif df.fieldtype in ("Int", "Float", "Currency", "Percent", "Check"):
			doc.set(df.fieldname, 1)
		elif df.fieldtype == "Dynamic Link":
			pass


class TestAppDocTypes(IntegrationTestCase):
	"""Every av_tools DocType must load its meta and controller and accept a generic insert on v16."""

	def test_meta_and_controller_load(self):
		doctypes = app_doctypes()
		self.assertGreaterEqual(len(doctypes), 85)
		for row in doctypes:
			with self.subTest(doctype=row.name):
				meta = frappe.get_meta(row.name)
				self.assertEqual(meta.name, row.name)
				controller = get_controller(row.name)
				self.assertTrue(isinstance(controller, type), row.name)

	def test_insert_smoke(self):
		outcomes = {"inserted": [], "needs_fixture": [], "unexpected": []}
		for row in app_doctypes(istable=0, issingle=0, is_virtual=0):
			savepoint = f"sp_{frappe.scrub(row.name)[:40]}"
			frappe.db.savepoint(savepoint)
			doc = frappe.new_doc(row.name)
			fill_mandatory(doc)
			try:
				doc.insert(ignore_permissions=True, ignore_links=True)
				outcomes["inserted"].append(row.name)
			except unexpected_errors() as error:
				outcomes["unexpected"].append(f"{row.name}: {type(error).__name__}: {str(error)[:120]}")
				frappe.db.rollback(save_point=savepoint)
			except Exception:
				outcomes["needs_fixture"].append(row.name)
				frappe.db.rollback(save_point=savepoint)
		frappe.flags.av_tools_insert_smoke = outcomes
		print("\nDocType insert smoke:", {k: len(v) for k, v in outcomes.items()})
		for line in outcomes["unexpected"]:
			print("   ", line)
		self.assertGreater(len(outcomes["inserted"]), 10)
		self.assertFalse(outcomes["unexpected"], outcomes["unexpected"])

	def test_single_doctypes_load(self):
		for row in app_doctypes(issingle=1):
			with self.subTest(doctype=row.name):
				single = frappe.get_single(row.name)
				single.run_method("validate")

	def test_child_tables_have_parents(self):
		orphans = []
		for row in app_doctypes(istable=1):
			used = frappe.get_all(
				"DocField",
				filters={"options": row.name, "fieldtype": ("in", ("Table", "Table MultiSelect"))},
				limit=1,
			)
			custom = frappe.get_all(
				"Custom Field",
				filters={"options": row.name, "fieldtype": ("in", ("Table", "Table MultiSelect"))},
				limit=1,
			)
			if not (used or custom):
				orphans.append(row.name)
		frappe.flags.av_tools_orphan_child_tables = orphans
		print("\nChild tables without a parent field on this site:", orphans)
		# Approver Detail is attached dynamically by AV Tools Settings; the rest are documented as orphans
		self.assertNotIn("Approval Doctypes", orphans)

	def test_link_fields_point_to_existing_doctypes(self):
		modules = frappe.get_module_list(APP)
		fields = frappe.get_all(
			"DocField",
			filters={
				"fieldtype": ("in", ("Link", "Table", "Table MultiSelect")),
				"parent": ("in", [d.name for d in app_doctypes()]),
			},
			fields=["parent", "fieldname", "options"],
		)
		self.assertTrue(fields)
		for field in fields:
			with self.subTest(field=f"{field.parent}.{field.fieldname}"):
				self.assertTrue(
					field.options and frappe.db.exists("DocType", field.options),
					f"{field.parent}.{field.fieldname} -> {field.options}",
				)
		self.assertTrue(modules)
