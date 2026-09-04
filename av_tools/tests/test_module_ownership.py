# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import frappe
from frappe.modules.patch_handler import get_patches_from_app
from frappe.tests import IntegrationTestCase

from av_tools.install import MIGRATION_PATCH_PREFIX
from av_tools.utils.legacy_settings import (
	SOURCE_DOCTYPE,
	TARGET_DOCTYPE,
	adopt_legacy_value,
	get_legacy_value,
)
from av_tools.utils.module_ownership import (
	execute,
	get_declared_modules,
	get_records_shipped_by_other_apps,
	get_stale_records,
)

APP = "av_tools"


class TestModuleOwnership(IntegrationTestCase):
	"""Records that moved here from csf_tz must resolve against an av_tools module."""

	def test_shipped_records_declare_an_av_tools_module(self):
		modules = set(frappe.get_module_list(APP))
		declared = get_declared_modules()
		self.assertTrue(declared, "no Report or Print Format files found in av_tools")

		for (doctype, name), module in declared.items():
			with self.subTest(record=f"{doctype} {name}"):
				self.assertIn(module, modules)

	def test_no_record_is_left_on_a_foreign_module(self):
		execute()
		self.assertEqual(get_stale_records(), [])

	def test_a_record_another_app_also_ships_is_left_alone(self):
		"""csf_tz keeps its own copy of several salary and permission reports."""
		shared = get_records_shipped_by_other_apps() & set(get_declared_modules())
		self.assertTrue(shared, "no shipped record overlaps another installed app")

		doctype, name = sorted(shared)[0]
		frappe.db.set_value(doctype, name, "module", "CSF TZ", update_modified=False)
		self.addCleanup(frappe.db.rollback)

		execute()

		self.assertEqual(frappe.db.get_value(doctype, name, "module"), "CSF TZ")

	def test_execute_rehomes_a_record_pointed_at_the_wrong_module(self):
		exclusive = sorted(set(get_declared_modules()) - get_records_shipped_by_other_apps())
		self.assertTrue(exclusive, "av_tools ships no record exclusively")
		doctype, name = exclusive[0]
		original = frappe.db.get_value(doctype, name, "module")

		frappe.db.set_value(doctype, name, "module", "CSF TZ", update_modified=False)
		self.assertTrue(get_stale_records())

		execute()
		self.assertEqual(frappe.db.get_value(doctype, name, "module"), original)


class TestMigrationPatchRecovery(IntegrationTestCase):
	"""install_app() marks app patches as done without running them; av_tools re-runs them."""

	def test_every_v1_0_patch_matches_the_recovery_prefix(self):
		v1_0_patches = [p for p in get_patches_from_app(APP) if ".patches.v1_0." in p]
		self.assertTrue(v1_0_patches)

		for patch in v1_0_patches:
			with self.subTest(patch=patch):
				self.assertTrue(patch.startswith(MIGRATION_PATCH_PREFIX))


class TestLegacySettings(IntegrationTestCase):
	"""CSF TZ Settings values must survive even though csf_tz dropped the fields."""

	def setUp(self):
		self.fieldname = "override_sales_invoice_qty"
		self.addCleanup(frappe.db.rollback)

	def test_legacy_value_is_adopted_and_removed(self):
		frappe.db.set_single_value(SOURCE_DOCTYPE, self.fieldname, 1)

		adopt_legacy_value(self.fieldname, default=0, as_int=True)

		self.assertEqual(frappe.db.get_single_value(TARGET_DOCTYPE, self.fieldname), 1)
		self.assertIsNone(get_legacy_value(self.fieldname))

	def test_missing_legacy_value_does_not_overwrite_a_configured_value(self):
		frappe.db.delete("Singles", {"doctype": SOURCE_DOCTYPE, "field": self.fieldname})
		frappe.db.set_single_value(TARGET_DOCTYPE, self.fieldname, 1)

		adopt_legacy_value(self.fieldname, default=0, as_int=True)

		self.assertEqual(frappe.db.get_single_value(TARGET_DOCTYPE, self.fieldname), 1)
