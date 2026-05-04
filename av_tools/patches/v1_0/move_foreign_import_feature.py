import frappe


FOREIGN_IMPORT_DOCTYPES = (
	"Foreign Import Transaction",
	"Foreign Import Settings",
	"Foreign Import LCV Details",
	"Foreign Import Payment Details",
	"Foreign Import Exchange Difference Details",
)

FOREIGN_IMPORT_REPORTS = ("Import Exchange Differences",)

CUSTOM_FIELDS = (
	"Purchase Invoice-section_break_foreign_import",
	"Purchase Invoice-foreign_import_tracker",
	"Purchase Invoice-enable_import_tracking",
	"Payment Entry-foreign_import_tracker",
	"Payment Entry-exchange_difference_amount",
	"Landed Cost Voucher-section_break_import_tracking",
	"Landed Cost Voucher-foreign_import_trackers",
	"Company-section_break_foreign_import",
	"Company-auto_create_import_tracker",
	"Company-import_exchange_threshold",
	"Supplier-track_import_exchanges",
	"Supplier-preferred_exchange_account",
	"Journal Entry-foreign_import_tracker",
)


def execute():
	for doctype_name in FOREIGN_IMPORT_DOCTYPES:
		if frappe.db.exists("DocType", doctype_name):
			frappe.db.set_value("DocType", doctype_name, "module", "Av Tools")

	for report_name in FOREIGN_IMPORT_REPORTS:
		if frappe.db.exists("Report", report_name):
			frappe.db.set_value("Report", report_name, "module", "Av Tools")

	for cf_name in CUSTOM_FIELDS:
		if frappe.db.exists("Custom Field", cf_name):
			frappe.db.set_value("Custom Field", cf_name, "module", "Av Tools")
