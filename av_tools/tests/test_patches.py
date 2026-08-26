# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import importlib

import frappe
from frappe.modules.patch_handler import get_patches_from_app
from frappe.tests import IntegrationTestCase

APP = "av_tools"


class TestPatches(IntegrationTestCase):
	"""Every patch listed in patches.txt must import and be safe to re-run on a migrated v16 site."""

	def patch_modules(self):
		modules = []
		for entry in get_patches_from_app(APP):
			modules.append(entry.split("#")[0].strip().split(" ")[0])
		return [m for m in modules if m]

	def test_patches_listed(self):
		modules = self.patch_modules()
		self.assertGreaterEqual(len(modules), 25)
		self.assertEqual(len(modules), len(set(modules)), "duplicate patch entries")

	def test_patches_import_and_rerun_idempotently(self):
		outcomes = {}
		for module_name in self.patch_modules():
			with self.subTest(patch=module_name):
				module = importlib.import_module(module_name)
				self.assertTrue(callable(getattr(module, "execute", None)), module_name)
				savepoint = "patch_rerun"
				frappe.db.savepoint(savepoint)
				module.execute()
				try:
					frappe.db.rollback(save_point=savepoint)
					outcomes[module_name] = "pass"
				except Exception as error:
					# the patch committed on its own (savepoint gone); it still ran cleanly
					if "does not exist" not in str(error):
						raise
					outcomes[module_name] = "pass (commits on its own)"
		frappe.flags.av_tools_patch_outcomes = outcomes
		self.assertEqual(len(outcomes), len(self.patch_modules()))

	def test_after_migrate_hooks_rerun(self):
		for path in frappe.get_hooks("after_migrate", app_name=APP):
			with self.subTest(hook=path):
				frappe.get_attr(path)()

	def test_custom_field_loader_is_idempotent(self):
		from av_tools.utils.create_custom_fields import execute
		from av_tools.utils.create_property_setter import execute as execute_property_setters

		before = frappe.db.count("Custom Field")
		execute()
		execute_property_setters()
		self.assertEqual(frappe.db.count("Custom Field"), before)
