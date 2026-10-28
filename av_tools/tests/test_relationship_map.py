"""Unit tests for the read-only relationship map traversal."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from av_tools import relationship_map as rm


class TestRelationshipMap(FrappeTestCase):
    def test_rejects_unsupported_doctype(self):
        with self.assertRaises(frappe.ValidationError):
            rm.get_relationship_map("User", "Administrator")

    def test_direction_and_document_states(self):
        records = {
            ("Purchase Order", "PO-TEST"): (1, "To Receive and Bill"),
            ("Purchase Invoice", "PI-TEST"): (0, "Draft"),
            ("Payment Entry", "PE-TEST"): (2, "Cancelled"),
        }
        links = {
            ("Purchase Invoice", "PI-TEST"): {
                ("Purchase Order", "PO-TEST", "Purchase Invoice", "PI-TEST"),
                ("Purchase Invoice", "PI-TEST", "Payment Entry", "PE-TEST"),
            },
            ("Purchase Order", "PO-TEST"): set(),
            ("Payment Entry", "PE-TEST"): set(),
        }

        def summary(dt, name):
            docstatus, status = records[(dt, name)]
            return {"id": dt + "::" + name, "doctype": dt, "name": name,
                    "docstatus": docstatus, "status": status}

        with (
            patch.object(rm.frappe.db, "exists", side_effect=lambda dt, name: (dt, name) in records),
            patch.object(rm, "_visible", return_value=True),
            patch.object(rm, "_summary", side_effect=summary),
            patch.object(rm, "_links_for", side_effect=lambda dt, name: links[(dt, name)]),
        ):
            result = rm.get_relationship_map("Purchase Invoice", "PI-TEST")

        self.assertEqual(len(result["nodes"]), 3)
        self.assertEqual({node["docstatus"] for node in result["nodes"]}, {0, 1, 2})
        self.assertIn(
            {"source": "Purchase Order::PO-TEST", "target": "Purchase Invoice::PI-TEST"},
            result["edges"],
        )

    def test_cannot_view_unpermitted_target(self):
        records = {
            ("Sales Order", "SO-TEST"),
            ("Sales Invoice", "SI-TEST"),
        }
        with (
            patch.object(rm.frappe.db, "exists", side_effect=lambda dt, name: (dt, name) in records),
            patch.object(rm, "_visible", side_effect=lambda dt, name: dt == "Sales Order"),
            patch.object(rm, "_summary", return_value={"id": "Sales Order::SO-TEST"}),
            patch.object(rm, "_links_for", return_value={
                ("Sales Order", "SO-TEST", "Sales Invoice", "SI-TEST"),
            }),
        ):
            result = rm.get_relationship_map("Sales Order", "SO-TEST")
        self.assertEqual(len(result["nodes"]), 1)
        self.assertFalse(result["edges"])

    def test_payment_entry_dynamic_forward_reference(self):
        from types import SimpleNamespace
        doc = SimpleNamespace(
            doctype="Payment Entry", name="PE-1",
            get=lambda key: [SimpleNamespace(reference_doctype="Sales Invoice", reference_name="SI-1")]
            if key == "references" else [],
        )
        self.assertIn(
            ("Sales Invoice", "SI-1", "Payment Entry", "PE-1"),
            rm._source_dynamic_references(doc),
        )

    def test_payment_entry_reverse_reference(self):
        from types import SimpleNamespace
        class Meta:
            def has_field(self, field):
                return field in ("reference_doctype", "reference_name")
        def get_all(doctype, **kwargs):
            self.assertEqual(doctype, "Payment Entry Reference")
            self.assertEqual(kwargs["filters"]["reference_doctype"], "Sales Invoice")
            self.assertEqual(kwargs["filters"]["reference_name"], "SI-1")
            return [SimpleNamespace(parent="PE-1")]
        with (
            patch.object(rm.frappe.db, "exists", side_effect=lambda dt, name: dt == "DocType" and name == "Payment Entry Reference"),
            patch.object(rm.frappe, "get_meta", return_value=Meta()),
            patch.object(rm.frappe, "get_all", side_effect=get_all),
        ):
            self.assertIn(
                ("Sales Invoice", "SI-1", "Payment Entry", "PE-1"),
                rm._dynamic_references("Sales Invoice", "SI-1"),
            )
