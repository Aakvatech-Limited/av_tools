# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.query_builder.functions import Date
from pypika import Case


def execute(filters=None):
	columns, data = [], []

	columns = [
		{
			"fieldname": "reference",
			"label": _("Reference"),
			"fieldtype": "Link",
			"options": "Customer Loan Assistance",
			"width": 150,
		},
		{
			"fieldname": "customer_type",
			"label": _("Lead / Customer"),
			"fieldtype": "Link",
			"options": "Doctype",
			"width": 150,
			"hidden": 1,
		},
		{
			"fieldname": "customer_reference",
			"label": _("Customer Reference"),
			"fieldtype": "Dynamic Link",
			"options": "customer_type",
			"width": 150,
		},
		{"fieldname": "customer_name", "label": _("Customer Name"), "fieldtype": "Data", "width": 150},
		{
			"fieldname": "loan_supplier",
			"label": _("Loan Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 150,
		},
		{"fieldname": "start_date", "label": _("Start Date"), "fieldtype": "Date", "width": 150},
		{"fieldname": "end_date", "label": _("End Date"), "fieldtype": "Date", "width": 150},
		{
			"fieldname": "loan_status",
			"label": _("Loan Status"),
			"fieldtype": "Dynamic Link",
			"options": "customer_type",
			"width": 150,
		},
	]

	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date must be before To Date {}").format(filters.to_date))

	loan = frappe.qb.DocType("Customer Loan Assistance")
	data = (
		frappe.qb.from_(loan)
		.select(
			loan.name.as_("reference"),
			Case().when(loan.customer.isnotnull(), "Customer").else_("Lead").as_("customer_type"),
			Case().when(loan.customer.isnotnull(), loan.customer).else_(loan.lead).as_("customer_reference"),
			Case().when(loan.customer.isnotnull(), loan.customer).else_(loan.lead_name).as_("customer_name"),
			loan.loan_supplier,
			Date(loan.creation).as_("start_date"),
			loan.completion_date.as_("end_date"),
			loan.loan_status,
		)
		.where(loan.creation.between(filters.from_date, filters.to_date))
	)
	if filters.loan_supplier:
		data = data.where(loan.loan_supplier == filters.loan_supplier)
	data = data.run(as_dict=True)
	return columns, data
