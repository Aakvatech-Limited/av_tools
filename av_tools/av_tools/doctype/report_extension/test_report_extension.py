# Copyright (c) 2025, Aakvatech and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools_hooks.query_report import get_script
from av_tools.patches.v1_0.migrate_report_extension_site_data import (
	SOURCE_DOCTYPE,
	TARGET_DOCTYPE,
	execute as migrate_report_extension_site_data,
)


class TestReportExtension(FrappeTestCase):
	def setUp(self):
		self.report_name = self.get_available_query_report()

	def test_get_script_uses_active_report_extension(self):
		report_extension = frappe.get_doc(
			{
				"doctype": TARGET_DOCTYPE,
				"report": self.report_name,
				"active": 1,
				"script": "frappe.query_reports['Test Report'] = {};",
				"html_format": "<div>custom report</div>",
			}
		).insert()
		self.addCleanup(report_extension.delete)

		result = get_script(self.report_name)

		self.assertEqual(result["script"], report_extension.script)
		self.assertEqual(result["html_format"], report_extension.html_format)

	def test_patch_migrates_legacy_report_extension_data_idempotently(self):
		if not frappe.db.exists("DocType", SOURCE_DOCTYPE):
			self.skipTest(f"{SOURCE_DOCTYPE} is not available on this site")

		source_doc = frappe.get_doc(
			{
				"doctype": SOURCE_DOCTYPE,
				"report": self.report_name,
				"active": 1,
				"script": "console.log('legacy script');",
				"html_format": "<div>legacy</div>",
			}
		).insert()
		self.addCleanup(source_doc.delete)

		migrate_report_extension_site_data()
		migrate_report_extension_site_data()

		target_doc = frappe.get_doc(TARGET_DOCTYPE, self.report_name)
		self.addCleanup(target_doc.delete)

		self.assertEqual(target_doc.report, self.report_name)
		self.assertEqual(target_doc.active, source_doc.active)
		self.assertEqual(target_doc.script, source_doc.script)
		self.assertEqual(target_doc.html_format, source_doc.html_format)

	def get_available_query_report(self):
		report_names = frappe.get_all(
			"Report",
			filters={"report_type": "Query Report", "disabled": 0},
			pluck="name",
			order_by="name asc",
		)

		for report_name in report_names:
			if frappe.db.exists(TARGET_DOCTYPE, report_name):
				continue
			if frappe.db.exists(SOURCE_DOCTYPE, report_name):
				continue
			return report_name

		self.skipTest("No query report without existing extension records is available")
