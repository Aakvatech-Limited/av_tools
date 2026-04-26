import frappe


PRINT_FORMATS = (
	"AV Jounrnal Entry",
	"AV Payment Entry Voucher",
	"AV Proforma Invoice",
	"AV Purchase Invoice",
	"AV Tax Invoice",
	"Payware Loan Agreement",
	"Payware Payslip",
	"Tally Format",
	"Withholding Certificate",
	"Withholding Certificate Multi Items",
	"AV TI VFD",
	"SI POS Inv",
)


def execute():
	for print_format in PRINT_FORMATS:
		if frappe.db.exists("Print Format", print_format):
			frappe.db.set_value("Print Format", print_format, "module", "Av Tools")
