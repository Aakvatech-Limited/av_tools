from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from av_tools.sales.customer_statement_renderer import (
    apply_statement_settings,
    get_customer_statement_pdf,
    get_email_defaults,
)


class TestCustomerStatementRenderer(FrappeTestCase):
    @patch("av_tools.sales.customer_statement_renderer.frappe.db.get_value")
    def test_apply_company_settings(self, get_value):
        get_value.return_value = "Company Letter Head"
        statement = frappe._dict(
            company="_Test Company",
            to_date="2026-09-18",
        )
        settings = frappe._dict(
            include_ageing=1,
            ageing_based_on="Due Date",
            default_orientation="Portrait",
            use_company_letter_head=1,
        )

        apply_statement_settings(statement, settings)

        self.assertEqual(statement.include_ageing, 1)
        self.assertEqual(statement.ageing_based_on, "Due Date")
        self.assertEqual(statement.posting_date, "2026-09-18")
        self.assertEqual(statement.orientation, "Portrait")
        self.assertEqual(statement.letter_head, "Company Letter Head")

    @patch("av_tools.sales.customer_statement_renderer.get_report_pdf")
    @patch(
        "av_tools.sales.customer_statement_renderer.get_customer_statement_settings",
        return_value=None,
    )
    def test_falls_back_to_erpnext_pdf_without_company_settings(
        self,
        _get_settings,
        get_report_pdf,
    ):
        get_report_pdf.return_value = b"%PDF-default"
        statement = frappe._dict(
            company="_Test Company",
            to_date="2026-09-18",
        )

        with patch(
            "av_tools.sales.customer_statement_renderer.frappe.db.get_value",
            return_value=None,
        ):
            pdf = get_customer_statement_pdf(statement)

        self.assertEqual(pdf, b"%PDF-default")
        get_report_pdf.assert_called_once_with(statement)

    @patch("av_tools.sales.customer_statement_renderer.frappe.render_template")
    @patch("av_tools.sales.customer_statement_renderer.frappe.get_cached_doc")
    @patch("av_tools.sales.customer_statement_renderer.get_customer_statement_settings")
    def test_company_email_templates_are_rendered(
        self,
        get_settings,
        get_cached_doc,
        render_template,
    ):
        get_settings.return_value = frappe._dict(
            default_email_subject="Statement - {{ customer.customer_name }}",
            default_email_message="Period {{ from_date }} to {{ to_date }}",
        )
        get_cached_doc.side_effect = [
            frappe._dict(customer_name="Test Customer"),
            frappe._dict(company_name="Test Company"),
        ]
        render_template.side_effect = [
            "Statement - Test Customer",
            "Period 2026-08-18 to 2026-09-18",
        ]

        result = get_email_defaults(
            company="_Test Company",
            customer="TEST-CUSTOMER",
            from_date="2026-08-18",
            to_date="2026-09-18",
        )

        self.assertEqual(result["subject"], "Statement - Test Customer")
        self.assertEqual(
            result["message"],
            "Period 2026-08-18 to 2026-09-18",
        )
