import frappe
from frappe import _
from frappe.model.document import Document

from av_tools.tax_detail_rebuild import service


class ItemWiseTaxDetailRebuild(Document):
	def before_insert(self):
		self.status = "Draft"
		self.set("entries", [])
		for field in (
			"scanned_count",
			"ready_count",
			"blocked_count",
			"unchanged_count",
			"rebuilt_count",
			"failed_count",
		):
			self.set(field, 0)
		for field in ("requested_by", "previewed_at", "started_at", "finished_at", "failure_reason"):
			self.set(field, None)

	def validate(self):
		service.validate_criteria(self)
		if not self.is_new():
			old = self.get_doc_before_save()
			if old.status != "Draft" or self.status != "Draft" or self.get("entries"):
				frappe.throw(_("Previewed requests and results are immutable. Create a new request."))
			protected = (
				"currency",
				"requested_by",
				"previewed_at",
				"started_at",
				"finished_at",
				"failure_reason",
				"scanned_count",
				"ready_count",
				"blocked_count",
				"unchanged_count",
				"rebuilt_count",
				"failed_count",
			)
			if any(self.get(field) != old.get(field) for field in protected):
				frappe.throw(_("Progress and audit fields are managed by the rebuild tool."))

	@frappe.whitelist(methods=["POST"])
	def preview(self):
		return service.preview(self.name)

	@frappe.whitelist(methods=["POST"])
	def rebuild(self):
		return service.queue_rebuild(self.name)
