import frappe


FULL_ACCESS_ROLE = "FULL ACCESS"
SETTINGS_DOCTYPE = "AV Tools Settings"
SETTING_FIELD = "enable_full_access_role"
ROLE_CHILD_DOCTYPE = "Has Role"
ROLE_PARENT_FIELD = "roles"


def is_full_access_enabled():
	return bool(frappe.db.get_single_value(SETTINGS_DOCTYPE, SETTING_FIELD))


def ensure_full_access_role():
	if frappe.db.exists("Role", FULL_ACCESS_ROLE):
		return

	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": FULL_ACCESS_ROLE,
			"desk_access": 1,
			"is_custom": 1,
		}
	).insert(ignore_permissions=True)


def get_module_app(module):
	if not module:
		return None

	try:
		return frappe.get_module_app(module)
	except Exception:
		return None


def is_frappe_module(module):
	return get_module_app(module) == "frappe"


def sync_full_access(app_name=None):
	"""Reconcile FULL ACCESS against all supported records when the feature is enabled."""
	if not is_full_access_enabled():
		return

	if getattr(frappe.flags, "in_full_access_sync", False):
		return

	frappe.flags.in_full_access_sync = True
	try:
		ensure_full_access_role()
		sync_doctypes(app_name=app_name)
		sync_reports(app_name=app_name)
		sync_pages(app_name=app_name)
		sync_workspaces(app_name=app_name)
		frappe.clear_cache()
	finally:
		frappe.flags.in_full_access_sync = False


def after_app_install(app_name):
	"""Apply FULL ACCESS immediately after a new app is installed."""
	if not is_full_access_enabled():
		return

	sync_full_access(app_name=app_name)


def on_doctype_change(doc, method=None):
	_sync_event_document("DocType", doc)


def on_report_change(doc, method=None):
	_sync_event_document("Report", doc)


def on_page_change(doc, method=None):
	_sync_event_document("Page", doc)


def on_workspace_change(doc, method=None):
	_sync_event_document("Workspace", doc)


def _sync_event_document(document_type, doc):
	if not is_full_access_enabled():
		return

	if getattr(frappe.flags, "in_full_access_sync", False):
		return

	frappe.flags.in_full_access_sync = True
	try:
		ensure_full_access_role()

		if document_type == "DocType":
			sync_doctype(doc)
		else:
			sync_role_document(document_type, doc)

		frappe.clear_cache()
	finally:
		frappe.flags.in_full_access_sync = False


def sync_doctypes(app_name=None):
	rows = frappe.get_all(
		"DocType",
		filters={"istable": 0},
		fields=["name", "module", "is_submittable", "istable"],
	)

	for row in rows:
		try:
			owner_app = get_module_app(row.module)
			if app_name and owner_app != app_name:
				continue

			sync_doctype(row)
		except Exception:
			_log_sync_error("DocType", row.name)


def sync_doctype(doc):
	if doc.get("istable"):
		remove_doctype_permission(doc.name)
		return

	if is_frappe_module(doc.get("module")):
		remove_doctype_permission(doc.name)
		return

	ensure_doctype_permission(doc)


def ensure_doctype_permission(doc):
	existing = frappe.get_all(
		"Custom DocPerm",
		filters={
			"parent": doc.name,
			"role": FULL_ACCESS_ROLE,
			"permlevel": 0,
			"if_owner": 0,
		},
		pluck="name",
	)

	values = {
		"read": 1,
		"write": 1,
		"create": 1,
		"delete": 1,
		"select": 1,
		"report": 1,
		"export": 1,
		"import": 1,
		"share": 1,
		"print": 1,
		"email": 1,
		"submit": 1 if doc.get("is_submittable") else 0,
		"cancel": 1 if doc.get("is_submittable") else 0,
		"amend": 1 if doc.get("is_submittable") else 0,
	}

	if existing:
		frappe.db.set_value("Custom DocPerm", existing[0], values, update_modified=False)
		for duplicate in existing[1:]:
			frappe.delete_doc("Custom DocPerm", duplicate, ignore_permissions=True, force=True)
		return

	permission = frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": doc.name,
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": FULL_ACCESS_ROLE,
			"permlevel": 0,
			"if_owner": 0,
			**values,
		}
	)
	permission.insert(ignore_permissions=True)


def remove_doctype_permission(doctype_name):
	names = frappe.get_all(
		"Custom DocPerm",
		filters={
			"parent": doctype_name,
			"role": FULL_ACCESS_ROLE,
		},
		pluck="name",
	)

	for name in names:
		try:
			frappe.delete_doc("Custom DocPerm", name, ignore_permissions=True, force=True)
		except Exception:
			_log_sync_error("Custom DocPerm", name)


def sync_reports(app_name=None):
	rows = frappe.get_all(
		"Report",
		fields=["name", "module", "ref_doctype"],
	)

	for row in rows:
		try:
			owner_app = get_record_app(row.module, row.ref_doctype)
			if app_name and owner_app != app_name:
				continue

			sync_role_document("Report", row)
		except Exception:
			_log_sync_error("Report", row.name)


def sync_pages(app_name=None):
	_sync_role_records("Page", app_name=app_name)


def sync_workspaces(app_name=None):
	_sync_role_records("Workspace", app_name=app_name)


def _sync_role_records(doctype, app_name=None):
	rows = frappe.get_all(doctype, fields=["name", "module"])

	for row in rows:
		try:
			owner_app = get_module_app(row.module)
			if app_name and owner_app != app_name:
				continue

			sync_role_document(doctype, row)
		except Exception:
			_log_sync_error(doctype, row.name)


def get_record_app(module, reference_doctype=None):
	owner_app = get_module_app(module)
	if owner_app:
		return owner_app

	if reference_doctype:
		reference_module = frappe.db.get_value("DocType", reference_doctype, "module")
		return get_module_app(reference_module)

	return None


def sync_role_document(parenttype, doc):
	reference_doctype = doc.get("ref_doctype") if parenttype == "Report" else None
	owner_app = get_record_app(doc.get("module"), reference_doctype)

	if owner_app == "frappe":
		remove_role_access(parenttype, doc.name)
		return

	ensure_role_access(parenttype, doc.name)


def ensure_role_access(parenttype, parent):
	if frappe.db.exists(
		ROLE_CHILD_DOCTYPE,
		{
			"parenttype": parenttype,
			"parent": parent,
			"parentfield": ROLE_PARENT_FIELD,
			"role": FULL_ACCESS_ROLE,
		},
	):
		return

	row = frappe.get_doc(
		{
			"doctype": ROLE_CHILD_DOCTYPE,
			"parenttype": parenttype,
			"parent": parent,
			"parentfield": ROLE_PARENT_FIELD,
			"role": FULL_ACCESS_ROLE,
		}
	)
	row.db_insert()


def remove_role_access(parenttype, parent):
	frappe.db.delete(
		ROLE_CHILD_DOCTYPE,
		{
			"parenttype": parenttype,
			"parent": parent,
			"parentfield": ROLE_PARENT_FIELD,
			"role": FULL_ACCESS_ROLE,
		},
	)


def _log_sync_error(doctype, name):
	frappe.log_error(
		title="FULL ACCESS synchronization failed",
		message=f"{doctype}: {name}\n\n{frappe.get_traceback()}",
	)
