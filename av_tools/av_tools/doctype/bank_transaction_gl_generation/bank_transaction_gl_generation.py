import frappe
from frappe import _
from frappe.model.document import Document

from av_tools.banking.generation import enqueue_generation, validate_request


class BankTransactionGLGeneration(Document):
	def before_insert(self):
		validate_request(self)
		self.status = "Queued"
		self.requested_by = frappe.session.user
		for field in ("scanned_count", "eligible_count", "created_count", "skipped_count", "failed_count"):
			self.set(field, 0)
		self.result_log = self.started_at = self.finished_at = None

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Generation requests are immutable. Create a new request instead."))

	def after_insert(self):
		enqueue_generation(self)
