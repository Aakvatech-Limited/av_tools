import frappe
from frappe import _
from frappe.model import core_doctypes_list
from frappe.permissions import setup_custom_perms
from frappe.utils.csvutils import getlink

excluded_doctype_list = ["Address", "Contact"]

# Roles that must never receive cascaded access: Guest is every anonymous visitor,
# All is every logged-in user including Website Users.
excluded_role_list = ["Guest", "All"]

GRANTING_PTYPES = ("read", "write", "create", "submit", "cancel", "amend", "delete")


def grant_dependant_access(doc, method):
	if getattr(frappe.flags, "in_full_access_sync", False):
		return
	if getattr(frappe.flags, "in_dependent_permission_setup", False):
		return
	if frappe.flags.in_install or frappe.flags.in_migrate:
		return
	enable_dependent_auto_permission = frappe.db.get_single_value(
		"AV Tools Settings", "enable_dependent_auto_permission"
	)
	if not enable_dependent_auto_permission:
		return
	if doc.dependent:
		frappe.msgprint(
			_(
				"Warning! {0} is a dependant doctype. If you wish to change access to it, remove it and add again."
			).format(getlink("DocType", doc.parent))
		)
		return
	if not is_cascade_allowed(doc):
		return
	fields = frappe.get_meta(doc.parent).fields
	doctypes_granted_access = []
	for field in fields:
		if field.get("fieldtype") in ["Link"]:
			if create_custom_docperm(field.options, doc.role, doc.parent):
				doctypes_granted_access += [field.options]
		if field.get("fieldtype") in ["Table"]:
			child_fields = frappe.get_meta(field.options).fields
			for child_field in child_fields:
				if child_field.get("fieldtype") in ["Link"]:
					if create_custom_docperm(child_field.options, doc.role, doc.parent):
						doctypes_granted_access += [child_field.options]

	if len(doctypes_granted_access) > 0:
		frappe.msgprint(
			_("Auto granted SELECT access to the following doctypes: " + str(doctypes_granted_access))
		)


def is_cascade_allowed(doc):
	"""Cascade only for rows that actually grant access, and never to guest or portal roles.

	A row saved with all rights unticked (a revocation) must not hand out SELECT on
	every linked doctype.
	"""
	if not any(doc.get(ptype) for ptype in GRANTING_PTYPES):
		return False
	if doc.role in excluded_role_list:
		return False
	if not frappe.db.get_value("Role", doc.role, "desk_access"):
		return False
	return True


def create_custom_docperm(doctype, role, parent):
	if doctype in excluded_doctype_list:
		return

	if doctype == parent or doctype in core_doctypes_list:
		return
	is_permission_exists = frappe.get_all("Custom DocPerm", filters={"parent": doctype, "role": role})
	if len(is_permission_exists) > 0:
		return False
	# The first Custom DocPerm row of a doctype replaces all of its standard DocPerm rows.
	# Copy the standard permissions first, so existing roles keep their access.
	frappe.flags.in_dependent_permission_setup = True
	try:
		setup_custom_perms(doctype)
	finally:
		frappe.flags.in_dependent_permission_setup = False
	if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role}):
		# The copied standard permissions already cover this role.
		return False
	custom_docperm = frappe.new_doc("Custom DocPerm")
	custom_docperm.parent = doctype
	custom_docperm.role = role
	custom_docperm.permlevel = 0
	custom_docperm.select = 1
	custom_docperm.read = 0
	custom_docperm.export = 0
	custom_docperm.dependent = 1
	custom_docperm.save()
	return True
