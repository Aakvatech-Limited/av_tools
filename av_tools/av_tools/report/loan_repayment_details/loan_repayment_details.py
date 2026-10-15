# Copyright (c) 2022, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe.query_builder.functions import Sum
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	loans = []
	data = []
	columns = get_columns(filters)

	repayments_from_salaries, repayments_not_from_salaries, all_repayments = get_repayments(filters)

	if repayments_from_salaries:
		loans += get__paid_loans(filters, repayments_from_salaries, True)

	if repayments_not_from_salaries:
		loans += get__paid_loans(filters, repayments_not_from_salaries, False)

	if all_repayments:
		loans += get_loans_not_started_to_be_paid(filters, all_repayments)

	custom_loan_repayment_records = get_custom_loan_repayment_not_from_salary(filters)

	for loan in loans:
		for custom_loan_repayment in custom_loan_repayment_records:
			if custom_loan_repayment.loan in loan.loan:
				loan.amount_paid_not_from_salary += flt(custom_loan_repayment.amount_paid_not_from_salary)

		loan.update(
			{
				"loan_balance": flt(loan.total_payable_amount)
				- flt(loan.amount_paid_from_salary)
				- flt(loan.amount_paid_not_from_salary)
				- flt(loan.write_off_amount)
			}
		)
		data.append(loan)

	return columns, data


def get_columns(filters):
	return [
		{"fieldname": "applicant", "fieldtype": "Data", "label": _("Applicant"), "width": "150px"},
		{"fieldname": "applicant_name", "fieldtype": "Data", "label": _("Applicant Name"), "width": "150px"},
		{"fieldname": "loan", "fieldtype": "Data", "label": _("Loan"), "width": "100px"},
		{
			"fieldname": "total_payable_amount",
			"fieldtype": "Currency",
			"label": _("Total Payable Amount"),
			"width": "150px",
		},
		{
			"fieldname": "amount_paid_from_salary",
			"fieldtype": "Currency",
			"label": _("Amount Paid From Salary"),
			"width": "150px",
		},
		{
			"fieldname": "amount_paid_not_from_salary",
			"fieldtype": "Currency",
			"label": _("Amount Paid not From Salary"),
			"width": "150px",
		},
		{
			"fieldname": "write_off_amount",
			"fieldtype": "Currency",
			"label": _("Write Off Amount"),
			"width": "150px",
		},
		{"fieldname": "loan_balance", "fieldtype": "Currency", "label": _("Loan Balance"), "width": "150px"},
	]


def _aggregate_loans(loan_names, from_salary=None, unpaid=False, employee=None):
	"""Aggregate loans by applicant while preserving report column semantics."""
	Loan = frappe.qb.DocType("Loan")
	query = (
		frappe.qb.from_(Loan)
		.select(
			Loan.name, Loan.applicant, Loan.applicant_name, Loan.posting_date,
			Loan.total_payment, Loan.total_amount_paid, Loan.written_off_amount,
		)
		.where(Loan.status != "Closed")
	)
	if unpaid:
		query = query.where(Loan.docstatus == 1)
		if loan_names:
			query = query.where(Loan.name.notin(loan_names))
		if employee:
			query = query.where(Loan.applicant == employee)
	else:
		if not loan_names:
			return []
		query = query.where(Loan.name.isin(loan_names))

	loans = query.orderby(Loan.posting_date).orderby(Loan.applicant).run(as_dict=True)
	write_offs = {}
	if unpaid and loans:
		WriteOff = frappe.qb.DocType("Loan Write Off")
		rows = (
			frappe.qb.from_(WriteOff)
			.select(WriteOff.loan, WriteOff.applicant, WriteOff.write_off_amount)
			.where(WriteOff.loan.isin([loan.name for loan in loans]))
			.run(as_dict=True)
		)
		for write_off in rows:
			key = (write_off.loan, write_off.applicant)
			write_offs[key] = write_offs.get(key, 0) + flt(write_off.write_off_amount)

	applicants = {}
	for loan in loans:
		key = loan.applicant
		if key not in applicants:
			applicants[key] = frappe._dict({
				"applicant": loan.applicant,
				"applicant_name": loan.applicant_name,
				"loan": "",
				"total_payable_amount": 0,
				"amount_paid_from_salary": 0 if from_salary is True else None,
				"amount_paid_not_from_salary": 0 if from_salary is False else None,
				"write_off_amount": 0,
				"loan_balance": None,
			})
		result = applicants[key]
		result.loan = result.loan + (", " if result.loan else "") + loan.name
		result.total_payable_amount += flt(loan.total_payment)
		if unpaid:
			result.write_off_amount += write_offs.get((loan.name, loan.applicant), 0)
		else:
			if from_salary:
				result.amount_paid_from_salary += flt(loan.total_amount_paid)
			else:
				result.amount_paid_not_from_salary += flt(loan.total_amount_paid)
			result.write_off_amount += flt(loan.written_off_amount)
	return list(applicants.values())


def get_loans_not_started_to_be_paid(filters, all_repayments):
	return _aggregate_loans(
		[repayment.against_loan for repayment in all_repayments],
		unpaid=True,
		employee=filters.get("employee"),
	)


def get__paid_loans(filters, repayments, from_salary):
	return _aggregate_loans(
		[repayment.against_loan for repayment in repayments], from_salary=from_salary
	)


def get_repayments(filters):
	employee = None
	if filters.get("employee"):
		employee = filters["employee"]
	else:
		employee = ["!=", ""]

	repayments_from_salaries = frappe.get_all(
		"Loan Repayment",
		filters={"loan_type": "Staff Loan", "repay_from_salary": 1, "docstatus": 1, "applicant": employee},
		fields=["Distinct(against_loan) as against_loan"],
		order_by="posting_date",
	)

	repayments_not_from_salaries = frappe.get_all(
		"Loan Repayment",
		filters={"loan_type": "Staff Loan", "repay_from_salary": 0, "docstatus": 1, "applicant": employee},
		fields=["Distinct(against_loan) as against_loan"],
		order_by="posting_date",
	)

	all_repayments = repayments_from_salaries + repayments_not_from_salaries

	return repayments_from_salaries, repayments_not_from_salaries, all_repayments


def get_custom_loan_repayment_not_from_salary(filters):
	Repayment = frappe.qb.DocType("Loan Repayment Not From Salary")
	return (
		frappe.qb.from_(Repayment)
		.select(Repayment.loan, Sum(Repayment.payment_amount).as_("amount_paid_not_from_salary"))
		.where(Repayment.loan != "")
		.groupby(Repayment.loan)
		.run(as_dict=True)
	)
