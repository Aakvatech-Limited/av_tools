"""Run on a disposable ERPNext v16 test site after bench migrate."""

import unittest

import frappe
from frappe.desk.notifications import get_child_doctypes_with_field, get_external_link_fieldname

from av_tools.asset_reconciliation.api import asset_capitalization_reconciliation_links


class TestNativeReconciliationIntegration(unittest.TestCase):
	def test_purchase_asset_settings_and_source_fields_are_installed(self):
		settings = frappe.get_meta("AV Tools Settings")
		self.assertEqual(settings.get_field("enable_no_time_appropriation_assets").default, "0")
		for fieldname in (
			"av_nta_purchase_invoice",
			"av_nta_purchase_invoice_item",
			"av_nta_unit_number",
			"av_nta_unit_key",
		):
			self.assertTrue(frappe.get_meta("Asset").has_field(fieldname))
		self.assertTrue(frappe.get_meta("Asset").get_field("av_nta_unit_key").unique)

	def test_standard_metadata_and_connections_are_registered(self):
		self.assertFalse(frappe.get_meta("Asset Capitalization Reconciliation").custom)
		for source in ("Asset", "Purchase Invoice", "Journal Entry"):
			with self.subTest(source=source):
				dashboard = frappe.get_meta(source).get_dashboard_data()
				self.assertTrue(
					any(
						"Asset Capitalization Reconciliation" in group.get("items", [])
						for group in dashboard.transactions
					)
				)
				fieldname = get_external_link_fieldname("Asset Capitalization Reconciliation", dashboard)
				expected = (
					"Asset Reconciliation Asset" if source == "Asset" else "Asset Reconciliation Source"
				)
				self.assertIn(
					expected, get_child_doctypes_with_field("Asset Capitalization Reconciliation", fieldname)
				)
		self.assertEqual(
			frappe.get_meta("Asset Reconciliation Source")
			.get_field("reconciliation_purchase_invoice")
			.options,
			"Purchase Invoice",
		)

	def test_report_executes_from_standard_app_module(self):
		report = frappe.get_doc("Report", "Fixed Asset Financial Reconciliation")
		self.assertEqual(report.is_standard, "Yes")
		self.assertEqual(report.module, "Av Tools")

	def test_guest_cannot_read_reconciliation_links(self):
		user = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises((frappe.PermissionError, frappe.DoesNotExistError)):
				asset_capitalization_reconciliation_links("Asset", "__missing_asset__")
		finally:
			frappe.set_user(user)
