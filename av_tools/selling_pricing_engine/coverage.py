"""Published-price coverage with bounded batch reads for a 5,000-SKU catalogue."""

from collections import Counter, defaultdict

import frappe
from frappe.utils import getdate

from av_tools.selling_pricing_engine import repository
from av_tools.selling_pricing_engine.access import LOCATION, check_link
from av_tools.selling_pricing_engine.calculation import number
from av_tools.selling_pricing_engine.locations import branch_for
from av_tools.selling_pricing_engine.report_scope import catalog, chunks, read_rows


class PublishedCoverage:
	def __init__(self, filters, config, items=None):
		self.filters = filters
		self.items = items if items is not None else catalog(filters)
		self.expanded = bool(config.get("enable_phase_2"))
		self.branch = (
			branch_for(filters.company, filters.warehouse, filters.get("branch")) if self.expanded else None
		)
		self.lists, self.factors = {}, None
		frappe.has_permission("Item Price", "read", throw=True)
		frappe.has_permission(LOCATION, "read", throw=True)

	def load(self, name):
		if name in self.lists:
			return self.lists[name]
		check_link("Price List", name)
		pl = frappe.get_cached_doc("Price List", name)
		if not pl.enabled or not pl.selling:
			raise ValueError("Coverage requires an enabled selling Price List")
		if self.expanded and name != self.filters.price_list:
			owner = frappe.db.get_value("Selling Price List Policy", {"price_list": name}, "company")
			if owner and owner != self.filters.company:
				raise ValueError("Alternate list belongs to another Company")
		standard, warehouse, branch = defaultdict(list), defaultdict(list), defaultdict(list)
		scanned = 0
		for batch in chunks([item.name for item in self.items]):
			criteria = {
				"price_list": name,
				"item_code": ["in", batch],
				"customer": ["is", "not set"],
				"supplier": ["is", "not set"],
				"batch_no": ["is", "not set"],
				"packing_unit": 0,
			}
			rows = read_rows(
				"Item Price",
				filters=criteria,
				fields=[
					"name",
					"item_code",
					"uom",
					"currency",
					"price_list_rate",
					"valid_from",
					"valid_upto",
					"customer",
					"supplier",
					"batch_no",
					"packing_unit",
				],
			)
			scanned += len(rows)
			if scanned > 100000:
				frappe.throw(
					"Narrow the Price List / Item Group: more than 100,000 price records match this coverage view."
				)
			for row in rows:
				if not self.effective(row):
					continue
				if not any(row.get(key) for key in ("customer", "supplier", "batch_no", "packing_unit")):
					standard[row.item_code].append(row)
			for scope, target, destination in (
				("warehouse", self.filters.warehouse, warehouse),
				("branch", self.branch, branch),
			):
				if not target:
					continue
				criteria = {
					"company": self.filters.company,
					"price_list": name,
					"item_code": ["in", batch],
					"enabled": 1,
					scope: target,
				}
				if scope == "branch":
					criteria["warehouse"] = ["is", "not set"]
				for row in read_rows(
					LOCATION,
					filters=criteria,
					fields=["name", "item_code", "uom", "currency", "rate", "valid_from", "valid_upto"],
				):
					if self.effective(row):
						destination[(row.item_code, row.uom)].append(row)
		policy = (
			frappe.db.get_value(
				"Selling Price List Policy",
				{"company": self.filters.company, "price_list": name, "enabled": 1},
				["runtime_fallback", "fallback_price_list"],
				as_dict=True,
			)
			if self.expanded
			else None
		)
		self.lists[name] = (pl, standard, warehouse, branch, policy)
		return self.lists[name]

	def factor(self, item, uom):
		if self.factors is None:
			self.factors = {}
			# Child reads are restricted to Item IDs already returned with permissions.
			for batch in chunks([row.name for row in self.items]):
				rows = frappe.get_all(
					"UOM Conversion Detail",
					filters={"parent": ["in", batch], "parenttype": "Item"},
					fields=["parent", "uom", "conversion_factor"],
					limit_page_length=0,
				)
				for row in rows:
					self.factors[(row.parent, row.uom)] = row.conversion_factor
		value = self.factors.get((item.name, uom))
		if not value or value <= 0:
			raise ValueError("No positive stock-to-selling-UOM conversion")
		return value

	def resolve(self, item, name, seen=None, currency=None, *, with_rate=False):
		seen = set(seen or ())
		if name in seen or len(seen) >= 25:
			raise ValueError("Cyclic or excessively deep alternate Price List chain")
		seen.add(name)
		pl, standard, warehouse, branch, policy = self.load(name)
		if currency and pl.currency != currency:
			raise ValueError("Alternate list currency mismatch")
		uom = item.sales_uom or item.stock_uom
		for label, candidates in (("Location override", warehouse), ("Branch override", branch)):
			price = repository.valid_price(candidates[(item.name, uom)], self.filters.as_on)
			if price:
				self.validate(price, pl.currency, price.rate)
				return (label, price.rate) if with_rate else label
		candidates = standard[item.name]
		price = repository.valid_price(
			[row for row in candidates if row.uom == uom or (not row.uom and uom == item.stock_uom)],
			self.filters.as_on,
		)
		factor = 1
		if not price and uom != item.stock_uom:
			price = repository.valid_price(
				[row for row in candidates if row.uom == item.stock_uom or not row.uom], self.filters.as_on
			)
			if price:
				factor = self.factor(item, uom) if not pl.get("price_not_uom_dependent") else 1
				self.factor(item, uom)
		if price:
			self.validate(price, pl.currency, price.price_list_rate)
			return (
				("Standard price", float(number(price.price_list_rate) * number(factor)))
				if with_rate
				else "Standard price"
			)
		if policy and policy.runtime_fallback and policy.fallback_price_list:
			label, rate = self.resolve(item, policy.fallback_price_list, seen, pl.currency, with_rate=True)
			label = "Alternate list" if label != "Missing" else "Missing"
			return (label, rate) if with_rate else label
		return ("Missing", None) if with_rate else "Missing"

	def effective(self, row):
		date = getdate(self.filters.as_on)
		return (not row.valid_from or getdate(row.valid_from) <= date) and (
			not row.valid_upto or getdate(row.valid_upto) >= date
		)

	@staticmethod
	def validate(row, currency, rate):
		if row.currency != currency or rate is None or number(rate) <= 0:
			raise ValueError("Invalid published price or currency")

	def counts(self):
		counts = Counter()
		self.load(self.filters.price_list)
		for item in self.items:
			try:
				counts[self.resolve(item, self.filters.price_list)] += 1
			except ValueError:
				counts["Invalid / overlapping"] += 1
		return counts
