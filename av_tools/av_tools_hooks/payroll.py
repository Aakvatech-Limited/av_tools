import frappe


@frappe.whitelist()
def get_payroll_employees(payroll_entry):
	Employee = frappe.qb.DocType("Payroll Employee Detail")
	return (
		frappe.qb.from_(Employee)
		.select(Employee.employee)
		.where(Employee.parent == payroll_entry)
		.run(as_dict=True)
	)


@frappe.whitelist()
def validate_payroll_entry_field(payroll_entry):
	payroll_entry = frappe.get_doc("Payroll Entry", payroll_entry)
	if payroll_entry.docstatus != 1:
		return False

	return True
