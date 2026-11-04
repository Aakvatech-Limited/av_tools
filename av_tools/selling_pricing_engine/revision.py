"""Server-owned preview and submission lifecycle for Selling Price Revision."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime

from av_tools.selling_pricing_engine import engine, publication, repository, validation
from av_tools.selling_pricing_engine.access import (
	REVISION,
	check_context,
	check_native_price_writes,
	settings,
)
from av_tools.selling_pricing_engine.calculation import number
from av_tools.selling_pricing_engine.import_prices import parse_prices

PARAMETERS = (
	"company",
	"price_list",
	"warehouse",
	"item_code",
	"uom",
	"valid_from",
	"valid_upto",
	"branch",
	"supplier",
	"item_group",
	"include_child_groups",
	"brand",
	"source_doctype",
	"source_document",
)
STAMP_FIELDS = ("status", "input_rows", "calculated_by", "calculated_on", "published_by", "published_on")
EDITABLE_ROW_FIELDS = {"selected", "acknowledge_unknown_margin", "review_note"}


def comparable(value, fieldtype=None):
	if fieldtype in ("Float", "Currency", "Percent", "Int", "Check"):
		return number(value or 0)
	if value and fieldtype == "Date":
		return getdate(value)
	if value and fieldtype == "Datetime":
		return get_datetime(value)
	return str(value or "")


class SellingPriceRevision(Document):
	def validate(self):
		check_context(self.company, self.price_list, self.warehouse, self.item_code)
		validation.dates(self)
		if any(self.get(key) for key in ("branch", "supplier", "item_group", "brand", "source_document")):
			from av_tools.selling_pricing_engine.policies import check_filters

			check_filters(self)
		if self.flags.get("spe_calculating"):
			return
		before = self.get_doc_before_save()
		if not before:
			if self.items or self.input_rows or self.status not in (None, "", "Draft"):
				frappe.throw(_("Save a blank draft, then use Calculate or Import Fixed Prices."))
			self.status = "Draft"
			return
		if any(
			comparable(self.get(key), "Datetime" if key.endswith("_on") else None)
			!= comparable(before.get(key), "Datetime" if key.endswith("_on") else None)
			for key in STAMP_FIELDS
		):
			frappe.throw(_("Calculation and publication fields are maintained by the engine."))
		if any(str(self.get(key) or "") != str(before.get(key) or "") for key in PARAMETERS):
			self.set("items", [])
			self.input_rows = None
			self.status = "Draft"
			self.calculated_by = self.calculated_on = None
			return
		if len(self.items) != len(before.items):
			frappe.throw(_("Use Calculate to regenerate revision rows."))
		meta = frappe.get_meta("Selling Price Revision Item")
		fields = meta.get_valid_columns()
		for current, old in zip(self.items, before.items, strict=True):
			for field in fields:
				if field in EDITABLE_ROW_FIELDS or field in {
					"creation",
					"modified",
					"modified_by",
					"docstatus",
				}:
					continue
				df = meta.get_field(field)
				kind = df.fieldtype if df else None
				if comparable(current.get(field), kind) != comparable(old.get(field), kind):
					frappe.throw(_("Calculated rows cannot be edited. Recalculate the revision."))

	@frappe.whitelist()
	def calculate(self):
		doc = self._working_copy()
		doc._calculate()
		self.reload()
		return {"rows": len(self.items), "status": self.status}

	@frappe.whitelist()
	def import_fixed_prices(self, csv_text):
		doc = self._working_copy()
		if doc.get("branch"):
			frappe.throw(
				_(
					"Fixed CSV import requires a standard or Warehouse revision. Use a Branch-scoped fixed rule and Calculate for Branch prices."
				)
			)
		config = settings(doc.company)
		policy = repository.policy_for(doc.company, doc.price_list)
		currency = frappe.get_cached_value("Price List", policy.price_list, "currency")
		try:
			inputs = parse_prices(
				csv_text,
				currency=currency,
				max_items=config.max_revision_items,
				precision=config.rate_precision,
			)
		except ValueError as exc:
			frappe.throw(str(exc))
		# Input values never directly write prices or rules. They enter the same preview.
		for row in inputs:
			check_context(doc.company, doc.price_list, row["warehouse"], row["item_code"])
		doc.input_rows = frappe.as_json(inputs)
		doc._calculate()
		self.reload()
		return {"rows": len(self.items), "status": self.status}

	def _working_copy(self):
		if self.is_new():
			frappe.throw(_("Save the revision before calculating."))
		doc = frappe.get_doc(REVISION, self.name)
		doc.check_permission("write")
		if doc.docstatus != 0:
			frappe.throw(_("Published revisions are immutable. Create a new revision."))
		return doc

	def _calculate(self):
		config = settings(self.company)
		if not config.get("enable_phase_2") and any(
			self.get(key) for key in ("branch", "supplier", "item_group", "brand", "source_document")
		):
			frappe.throw(_("Enable Expanded Pricing Policies before using Phase 2 filters."))
		check_native_price_writes()
		policy = repository.policy_for(self.company, self.price_list)
		inputs = frappe.parse_json(self.input_rows) if self.input_rows else None
		if not inputs:
			filters = {"disabled": 0, "is_sales_item": 1, "has_variants": 0, "is_fixed_asset": 0}
			if self.item_code:
				filters["name"] = self.item_code
			if config.get("enable_phase_2"):
				from av_tools.selling_pricing_engine.policies import item_filters

				filters = item_filters(self)
			items = frappe.get_list(
				"Item",
				filters=filters,
				fields=["name"],
				order_by="name",
				limit_page_length=config.max_revision_items + 1,
			)
			if len(items) > config.max_revision_items:
				frappe.throw(_("Too many Items for one revision. Filter an Item or import a smaller batch."))
			inputs = [{"item_code": row.name, "warehouse": self.warehouse, "uom": self.uom} for row in items]
		if not inputs:
			frappe.throw(_("No eligible sellable Items match this revision."))
		self.set("items", [])
		for row in inputs:
			context = {
				"item_code": row["item_code"],
				"warehouse": row.get("warehouse"),
				"uom": row.get("uom"),
				"valid_from": str(self.valid_from),
				"valid_upto": str(self.valid_upto) if self.valid_upto else None,
			}
			if config.get("enable_phase_2"):
				context.update(
					{key: self.get(key) for key in ("supplier", "source_doctype", "source_document")}
				)
				context["branch"] = self.get("branch") if not self.input_rows else None
			try:
				result = engine.calculate_row(config, policy, context, fixed_input=row.get("fixed_rate"))
			except (ValueError, frappe.ValidationError) as exc:
				result = {
					**context,
					"selected": 0,
					"result": "Blocked",
					"exception_reason": str(exc),
					"currency": frappe.get_cached_value("Price List", self.price_list, "currency"),
				}
			self.append("items", result)
		self.status, self.calculated_by, self.calculated_on = (
			"Calculated",
			frappe.session.user,
			now_datetime(),
		)
		self.flags.spe_calculating = True
		self.save()

	def before_submit(self):
		if self.status != "Calculated":
			frappe.throw(_("Calculate and review this revision before publishing."))
		config = settings(self.company, lock=True)
		check_native_price_writes()
		policy = repository.policy_for(self.company, self.price_list, lock=True)
		selected = [row for row in self.items if row.selected]
		if not selected:
			frappe.throw(_("Select at least one calculated price to publish."))
		# Check EVERY selected row before the first write. The surrounding submit
		# transaction rolls back prices, fixed rules and history together on failure.
		for row in selected:
			if row.result not in ("Ready", "Requires Review"):
				frappe.throw(_("Row {0} is blocked; deselect it or resolve the exception.").format(row.idx))
			context = {
				key: row.get(key) for key in ("item_code", "warehouse", "uom", "valid_from", "valid_upto")
			}
			context["valid_from"] = str(context["valid_from"])
			context["valid_upto"] = str(context["valid_upto"]) if context["valid_upto"] else None
			# Preserve the exact original context (including a defaulted UOM) in the recheck.
			snapshot = frappe.parse_json(row.calculation_snapshot)
			context = snapshot["context"]
			try:
				fresh = engine.calculate_row(
					config, policy, context, fixed_input=snapshot["fixed_input"], lock=True
				)
			except ValueError as exc:
				frappe.throw(str(exc))
			if fresh["calculation_hash"] != row.calculation_hash:
				frappe.throw(
					_(
						"Row {0}: cost, rules, configuration or existing price changed. Recalculate before publishing."
					).format(row.idx)
				)
			if fresh["result"] == "Blocked":
				frappe.throw(_("A price below minimum margin cannot be published."))
			if not row.cost_available and (
				not row.acknowledge_unknown_margin or len((row.review_note or "").strip()) < 10
			):
				frappe.throw(
					_(
						"Row {0}: acknowledge the unverified margin and enter a meaningful review note."
					).format(row.idx)
				)
		for row in selected:
			publication.publish_row(self, row)
		self.status, self.published_by, self.published_on = "Published", frappe.session.user, now_datetime()

	def before_cancel(self):
		frappe.throw(_("Published price history cannot be cancelled. Publish a correcting revision."))

	def on_trash(self):
		if self.docstatus or self.status == "Published":
			frappe.throw(_("Published price history cannot be deleted."))
