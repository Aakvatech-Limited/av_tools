import re
from unittest import TestCase
from unittest.mock import patch

from av_tools.av_tools_hooks import item_search


class TestItemSearch(TestCase):
	def test_split_search_terms(self):
		self.assertEqual(item_search.split_search_terms("blue chair"), ["blue", "chair"])
		self.assertEqual(item_search.split_search_terms("  blue   chair  "), ["blue", "chair"])
		self.assertEqual(item_search.split_search_terms(""), [])
		self.assertEqual(item_search.split_search_terms(None), [])

	def test_route_item_query(self):
		self.assertEqual(
			item_search.route_item_query("Item", item_search.ERP_ITEM_QUERY),
			item_search.AV_TOOLS_ITEM_QUERY,
		)
		self.assertEqual(item_search.route_item_query("Item", None), item_search.AV_TOOLS_ITEM_QUERY)
		self.assertEqual(
			item_search.route_item_query("Customer", "frappe.desk.search.search_widget"),
			"frappe.desk.search.search_widget",
		)

	def run_item_query(self, txt, match_condition=""):
		database = item_search.frappe.db
		with (
			patch.object(database, "count", return_value=10),
			patch.object(database, "sql", wraps=database.sql) as sql_spy,
			patch.object(item_search, "build_match_conditions", return_value=match_condition),
		):
			item_search.item_query.__wrapped__(
				doctype="Item",
				txt=txt,
				searchfield="name",
				start=0,
				page_len=20,
				filters={},
			)

		query, values = next(
			(call.args[0], call.args[1])
			for call in sql_spy.call_args_list
			if "FROM `tabItem`" in str(call.args[0])
		)
		return query, values

	def test_item_query_builds_multi_term_conditions(self):
		query, values = self.run_item_query("blue chair")
		params = {f"%({key})s": value for key, value in values.items()}

		for field in ("`item_name`", "`description`"):
			match = re.search(rf"{field} LIKE (%\(\w+\)s) AND {field} LIKE (%\(\w+\)s)", query)
			self.assertIsNotNone(match, field)
			self.assertEqual([params[match.group(1)], params[match.group(2)]], ["%blue%", "%chair%"])
		self.assertIn("%blue%chair%", values.values())

	def test_item_query_applies_user_permission_condition(self):
		condition = "`tabItem`.`item_group` in ('Allowed Group')"

		query, _values = self.run_item_query("chair", match_condition=condition)

		self.assertIn(f"({condition})", query)
