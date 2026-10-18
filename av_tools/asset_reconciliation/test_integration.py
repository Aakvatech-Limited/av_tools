"""Run on a disposable ERPNext v16 test site after bench migrate."""

import unittest

import frappe
from frappe.desk.form.linked_with import get_linked_doctypes

from av_tools.asset_reconciliation.api import asset_capitalization_reconciliation_links


class TestNativeReconciliationIntegration(unittest.TestCase):
    def test_standard_metadata_and_connections_are_registered(self):
        self.assertFalse(frappe.get_meta("Asset Capitalization Reconciliation").custom)
        for source in ("Asset", "Purchase Invoice", "Journal Entry"):
            with self.subTest(source=source):
                dashboard = frappe.get_meta(source).get_dashboard_data()
                self.assertTrue(any("Asset Capitalization Reconciliation" in group.get("items", [])
                                    for group in dashboard.transactions))
        asset_links = get_linked_doctypes("Asset")
        self.assertEqual(asset_links["Asset Capitalization Reconciliation"]["child_doctype"], "Asset Reconciliation Asset")
        self.assertEqual(frappe.get_meta("Asset Reconciliation Source").get_field("reconciliation_purchase_invoice").options,
                         "Purchase Invoice")

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
