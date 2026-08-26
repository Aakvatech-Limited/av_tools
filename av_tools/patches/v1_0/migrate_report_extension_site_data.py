import frappe


SOURCE_DOCTYPE = "AV Report Extension"
TARGET_DOCTYPE = "Report Extension"
FIELDS_TO_COPY = ("active", "script", "html_format")


def doctype_exists(doctype_name):
	return bool(frappe.db.exists("DocType", doctype_name))


def get_source_documents():
	return frappe.get_all(SOURCE_DOCTYPE, fields=["name", "report", *FIELDS_TO_COPY])


def upsert_report_extension(source_row):
	report_name = source_row.report or source_row.name
	target_name = frappe.db.exists(TARGET_DOCTYPE, report_name)

	if target_name:
		target_doc = frappe.get_doc(TARGET_DOCTYPE, target_name)
	else:
		target_doc = frappe.new_doc(TARGET_DOCTYPE)
		target_doc.report = report_name

	for fieldname in FIELDS_TO_COPY:
		target_doc.set(fieldname, source_row.get(fieldname))

	target_doc.save(ignore_permissions=True)


def execute():
	if doctype_exists(TARGET_DOCTYPE):
		frappe.db.set_value("DocType", TARGET_DOCTYPE, "module", "Av Tools", update_modified=False)

	if not doctype_exists(SOURCE_DOCTYPE) or not doctype_exists(TARGET_DOCTYPE):
		return

	for source_row in get_source_documents():
		upsert_report_extension(frappe._dict(source_row))
