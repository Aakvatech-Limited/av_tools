from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from av_tools.sales.page.customer_statement.customer_statement import (
    _parse_recipients,
    _validate_dates,
    get_statement_pdf,
)


class TestCustomerStatement(FrappeTestCase):
    def test_validate_dates_rejects_reverse_range(self):
        with self.assertRaises(frappe.ValidationError):
            _validate_dates("2026-09-18", "2026-08-18")

    def test_parse_recipients_supports_multiple_and_deduplicates(self):
        recipients = _parse_recipients(
            "primary@example.com",
            "finance@example.com; primary@example.com,owner@example.com",
        )

        self.assertEqual(
            recipients,
            [
                "primary@example.com",
                "finance@example.com",
                "owner@example.com",
            ],
        )

    @patch(
        "av_tools.sales.page.customer_statement.customer_statement._get_pdf",
        return_value=b"%PDF-test",
    )
    @patch(
        "av_tools.sales.page.customer_statement.customer_statement._get_filename",
        return_value="Customer Statement.pdf",
    )
    def test_get_statement_pdf_sets_inline_pdf_response(self, _filename, _pdf):
        original_response = frappe.local.response

        try:
            frappe.local.response = frappe._dict()

            get_statement_pdf(
                customer="TEST-CUSTOMER",
                from_date="2026-08-18",
                to_date="2026-09-18",
            )

            self.assertEqual(frappe.local.response.type, "pdf")
            self.assertEqual(
                frappe.local.response.filename,
                "Customer Statement.pdf",
            )
            self.assertEqual(
                frappe.local.response.filecontent,
                b"%PDF-test",
            )
        finally:
            frappe.local.response = original_response
