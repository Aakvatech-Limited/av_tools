from unittest import TestCase

from av_tools.api import item_lookups


class TestCollectPrices(TestCase):
	def collect(self, rates, max_records):
		rows = [{"rate": rate} for rate in rates]
		return item_lookups._collect_prices(rows, "rate", lambda row: row["rate"], max_records)

	def test_returns_at_most_max_records(self):
		self.assertEqual(self.collect([10, 20, 30, 40, 50], 2), [10, 20])

	def test_rows_without_rate_are_skipped_and_not_counted(self):
		self.assertEqual(self.collect([0, 10, None, 20, 30], 2), [10, 20])

	def test_returns_all_rows_below_the_limit(self):
		self.assertEqual(self.collect([10, 20], 20), [10, 20])
