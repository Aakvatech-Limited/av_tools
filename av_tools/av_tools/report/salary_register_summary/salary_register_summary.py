# Copyright (c) 2013, Aakvatech and contributors
# For license information, please see license.txt


import erpnext
import frappe
from frappe import _, msgprint
from frappe.query_builder.functions import Sum
from frappe.utils import flt
from frappe.utils.nestedset import get_descendants_of


def execute(filters=None):
	columns = [
		{"fieldname": "salary_component", "label": _("Salary Component"), "fieldtype": "Data", "width": 300},
		{"fieldname": "total", "label": _("Total"), "fieldtype": "Float", "width": 300},
	]
	data = get_data(filters)
	return columns, data


def get_data(filters=None):
	if not filters:
		filters = {}
	currency = None
	data = []
	if filters.get("currency"):
		currency = filters.get("currency")
	company_currency = erpnext.get_company_currency(filters.get("company"))
	salary_slips = get_salary_slips(filters, company_currency)
	if not salary_slips:
		return []

	blank_line = {"salary_component": "", "total": ""}
	total_employees = len(salary_slips)
	# frappe.msgprint(str(total_employees))
	total_employee_record = {"salary_component": "Total Employees", "total": total_employees}
	data.append(total_employee_record)
	data.append(blank_line)

	ss_basic_map = get_ss_basic_map(salary_slips, currency, company_currency)
	data.extend(ss_basic_map)
	t_basic = 0
	for basic in ss_basic_map:
		t_basic = t_basic + basic["total"]

	ss_earning_map = get_ss_earning_map(salary_slips, currency, company_currency)
	# data.extend(ss_earning_map)

	# frappe.msgprint(str(ss_earning_map))
	total_earnings = 0
	for earning in ss_earning_map:
		total_earnings = total_earnings + earning["total"]
	te_record = {"salary_component": "Total Allowances", "total": total_earnings}
	data.append(te_record)

	gross_pay = total_earnings + t_basic
	gp_record = {"salary_component": "GROSS PAY", "total": gross_pay}
	data.append(gp_record)

	ss_deduction_map = get_ss_ded_map(salary_slips, currency, company_currency)
	# data.extend(ss_deduction_map)

	total_deduction = 0
	for deduction in ss_deduction_map:
		total_deduction = total_deduction + deduction["total"]

	ded_record = {"salary_component": "Total Deductions", "total": total_deduction}
	data.append(ded_record)

	netpay = gross_pay + total_deduction
	np_record = {"salary_component": "NET PAY", "total": netpay}
	data.append(np_record)

	# ss_ded_map = get_ss_ded_map(salary_slips, currency, company_currency)
	# data.extend(ss_ded_map)
	return data


def get_salary_slips(filters, company_currency):
	Slip = frappe.qb.DocType("Salary Slip")
	query = frappe.qb.from_(Slip).select(Slip.star)
	if filters.get("docstatus"):
		query = query.where(
			Slip.docstatus == {"Draft": 0, "Submitted": 1, "Cancelled": 2}[filters.get("docstatus")]
		)
	if filters.get("from_date"):
		query = query.where(Slip.start_date >= filters.get("from_date"))
	if filters.get("to_date"):
		query = query.where(Slip.end_date <= filters.get("to_date"))
	if filters.get("company"):
		query = query.where(Slip.company == filters.get("company"))
	if filters.get("employee"):
		query = query.where(Slip.employee == filters.get("employee"))
	if filters.get("currency") and filters.get("currency") != company_currency:
		query = query.where(Slip.currency == filters.get("currency"))
	if filters.get("department") and filters.get("company"):
		query = query.where(
			Slip.department.isin(get_departments(filters.get("department"), filters.get("company")))
		)
	return query.orderby(Slip.employee).run(as_dict=True)


def _component_totals(salary_slips, parentfield, basic=None, negative=False):
	Detail = frappe.qb.DocType("Salary Detail")
	Slip = frappe.qb.DocType("Salary Slip")
	query = (
		frappe.qb.from_(Detail)
		.join(Slip)
		.on(Detail.parent == Slip.name)
		.select(Detail.salary_component, (Sum(Detail.amount) * (-1 if negative else 1)).as_("total"))
		.where(Detail.parent.isin([slip.name for slip in salary_slips]))
		.where(Detail.do_not_include_in_total == 0)
		.where(Detail.parentfield == parentfield)
	)
	if basic is True:
		query = query.where(Detail.salary_component == "Basic")
	if basic is False:
		query = query.where(Detail.salary_component != "Basic")
	return query.groupby(Detail.salary_component).orderby(Detail.salary_component).run(as_dict=True)


def get_ss_basic_map(salary_slips, currency, company_currency):
	return _component_totals(salary_slips, "earnings", basic=True)


def get_ss_earning_map(salary_slips, currency, company_currency):
	return _component_totals(salary_slips, "earnings", basic=False)


def get_ss_ded_map(salary_slips, currency, company_currency):
	return _component_totals(salary_slips, "deductions", negative=True)


def get_departments(department, company):
	departments_list = get_descendants_of("Department", department)
	departments_list.append(department)
	return departments_list
