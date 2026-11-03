from frappe.model.document import Document

from av_tools.selling_pricing_engine import validation


class SellingPriceRule(Document):
	def validate(self):
		validation.rule(self)
