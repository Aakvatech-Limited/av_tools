import frappe
from frappe.tests.utils import FrappeTestCase


class TestGenericAdminReports(FrappeTestCase):
	def test_reports_are_registered_under_av_tools(self):
		report_names = (
			"Schema Details",
			"Table Indexes",
			"SHOW PROCESSLIST",
			"Version Table Statistics",
			"Transaction Statistics",
			"Master Data Statistics",
		)

		for report_name in report_names:
			report = frappe.get_doc("Report", report_name)
			self.assertEqual(report.module, "Av Tools")
