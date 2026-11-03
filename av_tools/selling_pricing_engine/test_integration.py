"""Bench-only database checks. Run on an ERPNext v16 test site after migrate.

Requires ERPNext's _Test Company fixture. Cost retrieval is replaced with a
deterministic source so this suite checks real DocType storage, submit hooks,
fixed rules, date serialization and repeat publication independently of AP setup.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from av_tools.selling_pricing_engine import engine
from av_tools.selling_pricing_engine.access import LOCATION, POLICY, REVISION, RULE, SETTINGS


class TestSellingPricingPersistence(IntegrationTestCase):
	def setUp(self):
		from unittest.mock import patch

		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		if not frappe.db.exists("Company", "_Test Company"):
			self.skipTest("Load ERPNext's _Test Company fixture before running persistence tests")
		self.company = "_Test Company"
		self.currency = frappe.get_cached_value("Company", self.company, "default_currency")
		frappe.db.set_single_value("Stock Settings", "auto_insert_price_list_rate_if_missing", 0)
		self.config = (
			frappe.get_doc(SETTINGS, self.company)
			if frappe.db.exists(SETTINGS, self.company)
			else frappe.new_doc(SETTINGS)
		)
		self.config.update(
			{
				"company": self.company,
				"enabled": 1,
				"calculation_method": "Markup Percentage",
				"calculation_value": 20,
				"rounding_method": "No Rounding",
				"rounding_increment": 1,
				"minimum_margin": 10,
				"rate_precision": 6,
				"max_revision_items": 500,
				"manual_rate_role": "Sales Manager",
			}
		)
		self.config.save()
		self.price_list = (
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": "SPE Test " + frappe.generate_hash(length=8),
					"currency": self.currency,
					"selling": 1,
					"enabled": 1,
				}
			)
			.insert()
			.name
		)
		frappe.get_doc(
			{
				"doctype": POLICY,
				"company": self.company,
				"price_list": self.price_list,
				"enabled": 1,
				"calculation_mode": "Use Default",
				"rounding_mode": "Use Default",
				"rounding_increment": 1,
			}
		).insert()
		self.item = (
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "SPE-" + frappe.generate_hash(length=8),
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
					"is_purchase_item": 1,
				}
			)
			.insert()
			.name
		)
		self.warehouse = (
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": "SPE " + frappe.generate_hash(length=8),
					"company": self.company,
				}
			)
			.insert()
			.name
		)
		self.cost = {"cost_rate": 1000, "cost_source": "Test submitted purchase cost", "exchange_rate": 1}
		self.patch = patch.object(engine.store, "purchase_cost", side_effect=lambda *a, **k: dict(self.cost))
		self.patch.start()
		self.addCleanup(self.patch.stop)

	def revision(self, warehouse=None, day=None):
		return frappe.get_doc(
			{
				"doctype": REVISION,
				"company": self.company,
				"price_list": self.price_list,
				"item_code": self.item,
				"warehouse": warehouse,
				"uom": "Nos",
				"valid_from": day or today(),
			}
		).insert()

	def test_preview_publish_and_repeat_submit(self):
		doc = self.revision(self.warehouse)
		doc.calculate()
		self.assertEqual(doc.items[0].proposed_rate, 1200)
		self.assertFalse(frappe.db.exists(LOCATION, {"revision": doc.name}))
		# A browser round-trip must not fail immutable-field comparisons on dates/floats.
		doc = frappe.get_doc(frappe.parse_json(frappe.as_json(doc.as_dict())))
		doc.save()
		doc.submit()
		price = frappe.get_doc(LOCATION, doc.items[0].published_price)
		self.assertEqual(price.rate, 1200)
		self.assertEqual(price.company, self.company)
		self.assertEqual(doc.reload().items[0].result, "Published")
		doc.submit()
		self.assertEqual(frappe.db.count(LOCATION, {"revision": doc.name}), 1)

	def test_standard_price_preserves_previous_period(self):
		first = self.revision(day=add_days(today(), -1))
		first.calculate()
		first.submit()
		self.cost["cost_rate"] = 1100
		second = self.revision()
		second.calculate()
		second.submit()
		old = frappe.get_doc("Item Price", first.items[0].published_price)
		new = frappe.get_doc("Item Price", second.items[0].published_price)
		self.assertEqual(str(old.valid_upto), add_days(today(), -1))
		self.assertEqual(new.price_list_rate, 1320)
		self.assertEqual(new.custom_spe_revision, second.name)

	def test_fixed_import_survives_recalculation(self):
		doc = self.revision(self.warehouse)
		doc.import_fixed_prices(
			"item_code,warehouse,rate,uom,currency,tax_basis\n"
			+ f"{self.item},{self.warehouse},1725,Nos,{self.currency},Tax Exclusive"
		)
		doc.submit()
		self.assertTrue(frappe.db.exists(RULE, {"import_revision": doc.name}))
		self.cost["cost_rate"] = 700
		next_doc = self.revision(self.warehouse)
		next_doc.calculate()
		self.assertEqual(next_doc.items[0].proposed_rate, 1725)

	def test_stale_cost_cannot_publish(self):
		doc = self.revision(self.warehouse)
		doc.calculate()
		self.cost["cost_rate"] = 1100
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		self.assertFalse(frappe.db.exists(LOCATION, {"revision": doc.name}))

	def test_readonly_preview_tampering_rejected(self):
		doc = self.revision(self.warehouse)
		doc.calculate()
		doc.items[0].proposed_rate = 1
		with self.assertRaises(frappe.ValidationError):
			doc.save()
