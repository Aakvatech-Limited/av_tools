import inspect
import re
from unittest import TestCase
from unittest.mock import patch, sentinel

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

	def run_item_query(self, txt):
		database = item_search.frappe.db
		with (
			patch.object(database, "count", return_value=10),
			patch.object(database, "sql", wraps=database.sql) as sql_spy,
		):
			inspect.unwrap(item_search.item_query)(
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

	def test_item_query_respects_company_and_party_restrictions(self):
		for party_field, party_type, party_name in (
			("customer", "Customer", "Kamal Refinery Limited"),
			("supplier", "Supplier", "Test Supplier"),
		):
			with self.subTest(party_type=party_type):
				filters = {
					"is_sales_item": 1,
					"has_variants": 0,
					"company": "Aakvatech Limited",
					party_field: party_name,
				}
				with (
					patch.object(item_search.frappe, "get_meta") as get_meta,
					patch.object(item_search.frappe.qb, "get_query") as get_query,
					patch.object(item_search.frappe.db, "count", return_value=50000),
					patch.object(
						item_search, "get_restriction_criterion", return_value=sentinel.company_condition
					) as company_restriction,
					patch.object(
						item_search, "get_allowed_items_condition", return_value=sentinel.party_condition
					) as party_restriction,
				):
					get_meta.return_value.get_search_fields.return_value = ["item_name"]
					query = get_query.return_value
					for method in ("where", "orderby", "offset", "limit"):
						getattr(query, method).return_value = query
					query.run.return_value = []

					result = inspect.unwrap(item_search.item_query)(
						doctype="Item",
						txt="hosting",
						searchfield="name",
						start=0,
						page_len=20,
						filters=filters,
						reference_doctype="Quotation",
					)

					self.assertEqual(result, [])
					self.assertEqual(
						get_query.call_args.kwargs["filters"],
						{"is_sales_item": 1, "has_variants": 0},
					)
					self.assertEqual(get_query.call_args.kwargs["reference_doctype"], "Quotation")
					self.assertFalse(get_query.call_args.kwargs["ignore_permissions"])
					self.assertEqual(filters["company"], "Aakvatech Limited")
					self.assertEqual(filters[party_field], party_name)
					company_restriction.assert_called_once_with("Item", ["Aakvatech Limited"])
					party_restriction.assert_called_once_with(party_type, party_name)
					query.where.assert_any_call(sentinel.company_condition)
					query.where.assert_any_call(sentinel.party_condition)

	def test_item_query_allows_parties_without_specific_item_rules(self):
		with (
			patch.object(item_search.frappe, "get_meta") as get_meta,
			patch.object(item_search.frappe.qb, "get_query") as get_query,
			patch.object(item_search.frappe.db, "count", return_value=50000),
			patch.object(item_search, "get_allowed_items_condition", return_value=None) as party_restriction,
			patch.object(item_search, "get_restriction_criterion") as company_restriction,
		):
			get_meta.return_value.get_search_fields.return_value = ["item_name"]
			query = get_query.return_value
			for method in ("where", "orderby", "offset", "limit"):
				getattr(query, method).return_value = query
			query.run.return_value = []

			inspect.unwrap(item_search.item_query)(
				doctype="Item",
				txt="hosting",
				searchfield="name",
				start=0,
				page_len=20,
				filters={"customer": "Kamal Refinery Limited", "is_sales_item": 1},
			)

			self.assertEqual(get_query.call_args.kwargs["filters"], {"is_sales_item": 1})
			self.assertIsNone(get_query.call_args.kwargs["reference_doctype"])
			party_restriction.assert_called_once_with("Customer", "Kamal Refinery Limited")
			company_restriction.assert_not_called()
