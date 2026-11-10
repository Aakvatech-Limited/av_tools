"""Native Connections count/list checks on a disposable ERPNext v16 test site."""

import frappe
from frappe.desk.notifications import get_child_doctypes_with_field, get_external_links
from frappe.tests import IntegrationTestCase

from av_tools.tax_detail_rebuild.connections import ENTRY, LINK_FIELDS, TARGET, reference_fields


class TestRebuildConnectionsIntegration(IntegrationTestCase):
	def _request(self, source, invoice_name, duplicate=False):
		# Synthetic relation-only records: never create or modify financial invoices.
		# db_insert intentionally avoids the maintenance workflow's business validation.
		request = frappe.get_doc({"doctype": TARGET, "source_doctype": source, "status": "Previewed"})
		request.set_new_name()
		request.db_insert()
		for idx in range(2 if duplicate else 1):
			entry = frappe.get_doc(
				{
					"doctype": ENTRY,
					"parent": request.name,
					"parenttype": TARGET,
					"parentfield": "entries",
					"idx": idx + 1,
					"source_doctype": source,
					"source_invoice": invoice_name,
					"status": "Blocked" if idx else "Rebuilt",
					**reference_fields(source, invoice_name),
				}
			)
			entry.set_new_name()
			entry.db_insert()
		return request.name

	def test_child_links_count_distinct_requests_and_route_to_matching_list(self):
		name = "SYNTHETIC-TAX-LINK-" + frappe.generate_hash(length=10)
		purchase = self._request("Purchase Invoice", name, duplicate=True)
		sales = self._request("Sales Invoice", name)
		self._request("Purchase Invoice", name + "-OTHER")
		for source, expected in (("Purchase Invoice", purchase), ("Sales Invoice", sales)):
			with self.subTest(source=source):
				data = frappe.get_meta(source).get_dashboard_data()
				self.assertEqual(data.non_standard_fieldnames[TARGET], LINK_FIELDS[source])
				self.assertEqual(get_child_doctypes_with_field(TARGET, LINK_FIELDS[source]), [ENTRY])
				self.assertEqual(get_external_links(TARGET, name, data)["count"], 1)
				matches = frappe.get_all(
					TARGET, filters={LINK_FIELDS[source]: name}, pluck="name", distinct=True
				)
				self.assertEqual(matches, [expected])
