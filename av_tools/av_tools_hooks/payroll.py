import frappe


@frappe.whitelist()
def get_payroll_employees(payroll_entry):
	return frappe.db.sql(
		"""
		select employee
		from `tabPayroll Employee Detail`
		where parent = %s
		""",
		(payroll_entry,),
		as_dict=True,
	)


@frappe.whitelist()
def validate_payroll_entry_field(payroll_entry):
	payroll_entry = frappe.get_doc("Payroll Entry", payroll_entry)
	if payroll_entry.docstatus != 1:
		return False

	return True
