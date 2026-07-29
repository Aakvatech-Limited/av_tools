import frappe


@frappe.whitelist(methods=["POST"])
def get_payroll_employees(payroll_entry):
	payroll_employee_detail = frappe.qb.DocType("Payroll Employee Detail")
	return (
		frappe.qb.from_(payroll_employee_detail)
		.select(payroll_employee_detail.employee)
		.where(payroll_employee_detail.parent == payroll_entry)
	).run(as_dict=True)
def validate_payroll_entry_field(payroll_entry):
	payroll_entry = frappe.get_doc("Payroll Entry", payroll_entry)
	if payroll_entry.docstatus != 1:
		return False

	return True
