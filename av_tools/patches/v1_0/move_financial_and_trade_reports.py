import frappe

REPORTS = (
	"Customer GL Entries by Fiscal Year",
	"Customer Ledger Summary Multicurrency",
	"Depreciation Transaction Summary",
	"Purchase Cycle Report",
	"Purchase Report by Type",
	"Purchase Reports by Tax Category",
	"Purchases by Tax Category Summary",
	"Sales Cycle Report",
	"Sales Report by Type",
	"Sales Transaction Currency Recon",
	"Supplier GL Entries by Fiscal Year",
	"Supplier Ledger Summary Multicurrency",
	"Supplier Quotation Comparison Vertical",
)


def execute():
	for report_name in REPORTS:
		if frappe.db.exists("Report", report_name):
			frappe.db.set_value("Report", report_name, "module", "Av Tools")
