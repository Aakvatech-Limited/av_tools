# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools.doctype.implementation_handover_snapshot.implementation_handover_snapshot import (
    get_date_filters,
    validate_date_range,
)


class TestImplementationHandoverSnapshot(FrappeTestCase):
    def test_generate_snapshot_sets_json_rows_for_selected_sections(self):
        doc = frappe.get_doc(
            {
                "doctype": "Implementation Handover Snapshot",
                "customer": "_Test Customer",
                "table_qvkt": [
                    {
                        "reference": "Custom Field",
                    }
                ],
            }
        )

        doc.generate_snapshot()

        self.assertEqual(doc.site_name, frappe.local.site)
        self.assertEqual(len(doc.table_ldiu), 1)
        self.assertEqual(doc.table_ldiu[0].type, "Custom Field")

        payload = json.loads(doc.table_ldiu[0].json_type)
        self.assertIsInstance(payload, list)
        if payload:
            self.assertIn("name", payload[0])
            self.assertIn("dt", payload[0])

    def test_generate_snapshot_defaults_to_all_sections(self):
        doc = frappe.get_doc(
            {
                "doctype": "Implementation Handover Snapshot",
                "customer": "_Test Customer",
            }
        )

        doc.generate_snapshot()

        self.assertGreater(len(doc.table_ldiu), 1)
        self.assertEqual(doc.table_ldiu[0].type, "Client Script")

    def test_date_range_filters_modified_inclusive_days(self):
        doc = frappe.get_doc(
            {
                "doctype": "Implementation Handover Snapshot",
                "customer": "_Test Customer",
                "from_date": "2026-08-01",
                "to_date": "2026-08-07",
            }
        )

        self.assertEqual(
            get_date_filters(doc, "Custom Field"),
            {"modified": ["between", ["2026-08-01 00:00:00", "2026-08-07 23:59:59"]]},
        )

    def test_rejects_reversed_date_range(self):
        doc = frappe.get_doc(
            {
                "doctype": "Implementation Handover Snapshot",
                "customer": "_Test Customer",
                "from_date": "2026-08-07",
                "to_date": "2026-08-01",
            }
        )

        self.assertRaises(frappe.ValidationError, validate_date_range, doc)
