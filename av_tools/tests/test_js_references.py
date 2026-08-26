# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import json
import os
import re

import frappe
from frappe.model.base_document import get_controller
from frappe.tests import IntegrationTestCase

APP = "av_tools"
DOTTED = re.compile(
	r"""(?:method\s*:\s*|frappe\.xcall\(\s*|frappe\.call\(\s*)["']((?:av_tools|erpnext|frappe|hrms)\.[\w.]+)["']"""
)
DOC_METHOD = re.compile(r"""frm\.call\(\s*\{[^}]*?method\s*:\s*["'](\w+)["']""", re.S)
DOC_METHOD_ALT = re.compile(r"""frm\.call\(\s*["'](\w+)["']""")
REMOVED_CLIENT_APIS = [
	"frappe.ui.form.Controller.extend",
	"frappe.ui.form.Controller",
	"$c_obj(",
	"frappe.ui.toolbar.clear_cache",
	"cur_frm.cscript.onload_post_render =",
	"frappe.model.with_doctype(cur_frm",
]


def js_files():
	root = frappe.get_app_path(APP)
	for base, _, files in os.walk(root):
		if "/public/dist" in base or "node_modules" in base:
			continue
		for name in files:
			if name.endswith(".js"):
				yield os.path.join(base, name)


class TestJsServerReferences(IntegrationTestCase):
	"""Every server method a JS file calls must exist and be whitelisted; removed v16 client APIs must not be used."""

	def test_dotted_method_paths_exist_and_are_whitelisted(self):
		checked = 0
		for path in js_files():
			with open(path) as handle:
				source = handle.read()
			for method in set(DOTTED.findall(source)):
				with self.subTest(file=os.path.relpath(path, frappe.get_app_path(APP)), method=method):
					function = frappe.get_attr(method)
					self.assertTrue(callable(function), method)
					self.assertIn(function, frappe.whitelisted, f"{method} is not whitelisted")
					checked += 1
		frappe.flags.av_tools_js_refs_checked = checked
		self.assertGreater(checked, 20)

	def test_document_methods_called_by_forms_are_whitelisted(self):
		checked = 0
		for path in js_files():
			match = re.search(r"/doctype/([a-z0-9_]+)/\1\.js$", path)
			if not match:
				continue
			with open(path[:-3] + ".json") as handle:
				doctype = json.load(handle)["name"]
			if not frappe.db.exists("DocType", doctype):
				continue
			with open(path) as handle:
				source = handle.read()
			controller = get_controller(doctype)
			for method in set(DOC_METHOD.findall(source)) | set(DOC_METHOD_ALT.findall(source)):
				if "." in method:
					continue
				with self.subTest(doctype=doctype, method=method):
					function = getattr(controller, method, None)
					self.assertTrue(callable(function), f"{doctype}.{method} missing on controller")
					self.assertIn(function, frappe.whitelisted, f"{doctype}.{method} is not whitelisted")
					checked += 1
		self.assertGreater(checked, 3)

	def test_no_removed_client_apis(self):
		for path in js_files():
			with open(path) as handle:
				source = handle.read()
			for api in REMOVED_CLIENT_APIS:
				with self.subTest(file=os.path.relpath(path, frappe.get_app_path(APP)), api=api):
					self.assertNotIn(api, source)

	def test_js_files_parse(self):
		import subprocess

		for path in js_files():
			with self.subTest(file=os.path.relpath(path, frappe.get_app_path(APP))):
				result = subprocess.run(["node", "--check", path], capture_output=True, text=True)
				self.assertEqual(result.returncode, 0, result.stderr[:300])
