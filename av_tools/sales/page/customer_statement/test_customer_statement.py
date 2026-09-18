from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from av_tools.sales.page.customer_statement.customer_statement import (
    _build_statement_doc,
    _parse_recipients,
    _validate_dates,
    get_statement_pdf,
)


class TestCustomerStatement(FrappeTestCase):
    @patch(
        "av_tools.sales.page.customer_statement.customer_statement._get_company",
        return_value="_Test Company",
    )
    @patch("frappe.has_permission")
    @patch("frappe.get_cached_doc")
    def test_statement_uses_posting_date_ageing(
        self,
        get_cached_doc,
        _has_permission,
        _get_company,
    ):
        get_cached_doc.return_value = frappe._dict(
            name="TEST-CUSTOMER",
            customer_name="Test Customer",
            email_id="accounts@example.com",
        )

        statement = _build_statement_doc(
            customer="TEST-CUSTOMER",
            from_date="2026-08-18",
            to_date="2026-09-18",
        )

        self.assertEqual(statement.include_ageing, 1)
        self.assertEqual(statement.ageing_based_on, "Posting Date")
        self.assertEqual(statement.posting_date, "2026-09-18")

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
