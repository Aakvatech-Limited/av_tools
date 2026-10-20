"""Regression tests for scoped Asset cleanup dependency discovery."""

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from av_tools.asset_reconciliation.asset_cleanup import OWNED_TYPES, incoming


class TestAssetCleanupLinks(FrappeTestCase):
	@patch("frappe.desk.form.linked_with.get_referencing_documents")
	@patch("frappe.desk.form.linked_with.get_references_across_doctypes")
	@patch("frappe.get_hooks", return_value=[])
	def test_scopes_reference_discovery_to_owned_types(self, _hooks, references, documents):
		references.return_value = {
			"Asset": [{"doctype": "Asset Movement Detail", "fieldname": "asset"}]
		}
		documents.return_value = {
			"Asset Movement": ["MOVE-0001"],
			"Unrelated DocType": ["OTHER-0001"],
		}

		result = incoming("Asset", "ASSET-0001")

		references.assert_called_once_with(
			to_doctypes=["Asset"], limit_link_doctypes=sorted(OWNED_TYPES)
		)
		self.assertEqual(result, {("Asset Movement", "MOVE-0001")})

	@patch("frappe.desk.form.linked_with.get_referencing_documents")
	@patch("frappe.desk.form.linked_with.get_references_across_doctypes")
	@patch("frappe.get_hooks", return_value=[])
	def test_empty_references_return_no_dependencies(self, _hooks, references, documents):
		references.return_value = {}
		self.assertEqual(incoming("Asset", "ASSET-0001"), set())
		documents.assert_not_called()
