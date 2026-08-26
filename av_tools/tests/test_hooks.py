# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import os

import frappe
from frappe.model.base_document import get_controller
from frappe.tests import IntegrationTestCase

APP = "av_tools"


def iter_dotted_paths(value):
	if isinstance(value, str):
		yield value
	elif isinstance(value, dict):
		for item in value.values():
			yield from iter_dotted_paths(item)
	elif isinstance(value, list | tuple):
		for item in value:
			yield from iter_dotted_paths(item)


class TestHooks(IntegrationTestCase):
	"""Every hook in hooks.py must resolve to a callable and every asset must exist on disk."""

	hook_keys = (
		"doc_events",
		"scheduler_events",
		"override_whitelisted_methods",
		"override_doctype_class",
		"before_install",
		"after_install",
		"after_migrate",
		"extend_bootinfo",
		"jinja",
	)

	def app_hooks(self):
		return frappe.get_hooks(app_name=APP)

	def test_dotted_paths_resolve(self):
		hooks = self.app_hooks()
		checked = 0
		for key in self.hook_keys:
			for path in iter_dotted_paths(hooks.get(key)):
				if key == "override_doctype_class" or "." not in path:
					continue
				with self.subTest(hook=key, path=path):
					self.assertTrue(callable(frappe.get_attr(path)), path)
					checked += 1
		self.assertGreater(checked, 40)

	def test_override_doctype_class_extends_original(self):
		for doctype, class_path in self.app_hooks().get("override_doctype_class", {}).items():
			for path in iter_dotted_paths(class_path):
				override = frappe.get_attr(path)
				original = get_controller(doctype)
				self.assertTrue(isinstance(override, type))
				self.assertTrue(
					issubclass(override, original.__mro__[1]), f"{path} must extend the {doctype} controller"
				)

	def test_override_whitelisted_methods_pair_with_originals(self):
		for original, override in self.app_hooks().get("override_whitelisted_methods", {}).items():
			with self.subTest(original=original):
				original_fn = frappe.get_attr(original)
				override_fn = frappe.get_attr(override[0] if isinstance(override, list) else override)
				self.assertIn(original_fn, frappe.whitelisted)
				self.assertIn(override_fn, frappe.whitelisted)

	def test_doc_event_doctypes_exist(self):
		for doctype in self.app_hooks().get("doc_events", {}):
			if doctype == "*":
				continue
			with self.subTest(doctype=doctype):
				self.assertTrue(frappe.db.exists("DocType", doctype), doctype)

	def test_include_assets_exist(self):
		hooks = self.app_hooks()
		public = frappe.get_app_path(APP, "public")
		for entry in (
			hooks.get("app_include_js", [])
			+ hooks.get("app_include_css", [])
			+ hooks.get("web_include_css", [])
		):
			with self.subTest(asset=entry):
				if entry.startswith("/assets/av_tools/"):
					self.assertTrue(
						os.path.exists(os.path.join(public, entry.split("/assets/av_tools/")[1])), entry
					)
				else:
					self.assertTrue(os.path.exists(os.path.join(public, entry)), entry)

	def test_doctype_js_files_exist(self):
		for doctype, files in self.app_hooks().get("doctype_js", {}).items():
			self.assertTrue(frappe.db.exists("DocType", doctype), doctype)
			for relative in files if isinstance(files, list) else [files]:
				with self.subTest(file=relative):
					self.assertTrue(os.path.exists(frappe.get_app_path(APP, relative)), relative)

	def test_scheduler_events_are_registered(self):
		events = self.app_hooks().get("scheduler_events", {})
		self.assertIn("daily", events)
		self.assertIn("cron", events)
		for path in iter_dotted_paths(events):
			if "." in path:
				self.assertTrue(callable(frappe.get_attr(path)))

	def test_modules_registered(self):
		for module in frappe.get_module_list(APP):
			with self.subTest(module=module):
				self.assertEqual(frappe.db.get_value("Module Def", module, "app_name"), APP)

	def test_boot_session_hook(self):
		bootinfo = frappe._dict()
		frappe.get_attr(self.app_hooks()["extend_bootinfo"][0])(bootinfo)
		self.assertIsInstance(bootinfo.parallel_approval_doctypes, list)
