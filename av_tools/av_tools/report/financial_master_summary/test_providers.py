from frappe import _dict
from frappe.tests.utils import FrappeTestCase

from av_tools.av_tools.report.financial_master_summary.providers import (
	_asset_values,
	_make_master_row,
	get_provider,
)


class TestFinancialDrilldownProviders(FrappeTestCase):
	def test_provider_mapping_is_conservative(self):
		self.assertEqual(get_provider("Stock"), "Stock")
		self.assertEqual(get_provider("Fixed Asset"), "Asset")
		self.assertEqual(get_provider("Accumulated Depreciation"), "Asset")
		self.assertEqual(get_provider("Depreciation"), "Asset")
		self.assertIsNone(get_provider("Cost of Goods Sold"))
		self.assertIsNone(get_provider("Income Account"))

	def test_stock_master_row_preserves_drilldown_context(self):
		row = _make_master_row(
			label="ITEM-001",
			master_type="Item",
			master_value="ITEM-001",
			indent=2,
			values={
				"opening_value": 10,
				"increase_value": 20,
				"decrease_value": 5,
				"closing_value": 25,
			},
			warehouse="Stores - TC",
			item_group="Products",
			item="ITEM-001",
		)

		self.assertEqual(row.provider, "Stock")
		self.assertEqual(row.warehouse, "Stores - TC")
		self.assertEqual(row.item_group, "Products")
		self.assertEqual(row.item, "ITEM-001")
		self.assertEqual(row.closing_value, 25)

	def test_asset_values_follow_selected_account_semantics(self):
		row = _dict(
			value_as_on_from_date=1000,
			value_of_new_purchase=300,
			adjustment_during_period=20,
			value_of_sold_asset=100,
			value_of_scrapped_asset=50,
			value_of_capitalized_asset=0,
			value_as_on_to_date=1170,
			accumulated_depreciation_as_on_from_date=200,
			depreciation_amount_during_the_period=80,
			depreciation_eliminated_during_the_period=10,
			depreciation_eliminated_via_reversal=0,
			accumulated_depreciation_as_on_to_date=270,
		)

		fixed_asset = _asset_values(row, "Fixed Asset")
		accumulated = _asset_values(row, "Accumulated Depreciation")
		depreciation = _asset_values(row, "Depreciation")

		self.assertEqual(fixed_asset["closing_value"], 1170)
		self.assertEqual(accumulated["closing_value"], 270)
		self.assertEqual(depreciation["increase_value"], 80)
