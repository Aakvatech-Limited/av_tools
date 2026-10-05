from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from av_tools.av_tools.report.manufacturing_bom_variance.manufacturing_bom_variance import (
	get_monthly_summary,
	summarize_detail_rows,
)


class TestManufacturingBomVariance(FrappeTestCase):
	def test_item_summary_keeps_uoms_separate(self):
		rows = [
			frappe._dict(
				item_code="RM-001",
				uom="Kg",
				actual_qty=12,
				bom_guided_qty=10,
				variance_qty=2,
			),
			frappe._dict(
				item_code="RM-001",
				uom="Nos",
				actual_qty=9,
				bom_guided_qty=10,
				variance_qty=-1,
			),
		]

		summary = summarize_detail_rows(rows)

		self.assertEqual(len(summary), 2)
		self.assertEqual({row.uom for row in summary}, {"Kg", "Nos"})

	def test_summary_calculates_actual_vs_bom_statistics(self):
		rows = [
			frappe._dict(
				item_code="RM-001",
				uom="Kg",
				actual_qty=12,
				bom_guided_qty=10,
				variance_qty=2,
			),
			frappe._dict(
				item_code="RM-001",
				uom="Kg",
				actual_qty=8,
				bom_guided_qty=10,
				variance_qty=-2,
			),
		]

		summary = summarize_detail_rows(rows)[0]

		self.assertEqual(summary.actual_qty, 20)
		self.assertEqual(summary.bom_guided_qty, 20)
		self.assertEqual(summary.variance_qty, 0)
		self.assertEqual(summary.absolute_variance_percent, 20)
		self.assertEqual(summary.efficiency_percent, 100)

	@patch(
		"av_tools.av_tools.report.manufacturing_bom_variance.manufacturing_bom_variance.get_detail_data"
	)
	def test_monthly_summary_averages_item_normalized_percentages(self, get_detail_data):
		get_detail_data.return_value = [
			frappe._dict(
				posting_date=getdate("2026-09-01"),
				item_code="RM-001",
				uom="Kg",
				actual_qty=12,
				bom_guided_qty=10,
				variance_qty=2,
			),
			frappe._dict(
				posting_date=getdate("2026-09-02"),
				item_code="RM-002",
				uom="Nos",
				actual_qty=8,
				bom_guided_qty=10,
				variance_qty=-2,
			),
		]

		data = get_monthly_summary({"from_date": "2026-09-01", "to_date": "2026-09-30"})

		self.assertEqual(len(data), 1)
		self.assertEqual(data[0].month, "2026-09")
		self.assertAlmostEqual(data[0].absolute_variance_percent, 20)
		self.assertAlmostEqual(data[0].consumption_index_percent, 100)
		self.assertAlmostEqual(data[0].efficiency_percent, (10 / 12 * 100 + 10 / 8 * 100) / 2)
