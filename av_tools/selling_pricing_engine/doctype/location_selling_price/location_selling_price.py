from frappe.model.document import Document

from av_tools.selling_pricing_engine import validation


class LocationSellingPrice(Document):
	def validate(self):
		validation.location(self)
