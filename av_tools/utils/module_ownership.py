"""Keep Report and Print Format records pointing at the module that ships their files."""

import json
import os

import frappe

APP_NAME = "av_tools"
OWNED_DOCTYPES = ("Report", "Print Format")


def read_definition(folder, slug):
	path = os.path.join(folder, slug, f"{slug}.json")
	if not os.path.isfile(path):
		return None

	with open(path) as definition_file:
		definition = json.load(definition_file)

	if not definition.get("name") or not definition.get("module"):
		return None

	return definition


def get_declared_modules():
	"""Map every Report and Print Format shipped by av_tools to the module its file declares."""
	declared = {}
	for module in frappe.get_module_list(APP_NAME):
		for doctype in OWNED_DOCTYPES:
			folder = frappe.get_app_path(APP_NAME, frappe.scrub(module), frappe.scrub(doctype))
			if not os.path.isdir(folder):
				continue

			for slug in os.listdir(folder):
				definition = read_definition(folder, slug)
				if definition:
					declared[(doctype, definition["name"])] = definition["module"]

	return declared


def get_stale_records():
	"""Records whose stored module differs from the module their file declares."""
	stale = []
	for (doctype, name), module in get_declared_modules().items():
		stored_module = frappe.db.get_value(doctype, name, "module")
		if stored_module and stored_module != module:
			stale.append((doctype, name, stored_module, module))

	return stale


def execute():
	"""Re-home records that moved here from another app.

	Frappe skips importing a file whose `modified` timestamp still matches the database, so a
	Report or Print Format carried over from csf_tz keeps a module csf_tz no longer ships. The
	stored module decides which app frappe loads the code from, so those records fail to run
	until the module is corrected.
	"""
	for doctype, name, stored_module, module in get_stale_records():
		frappe.db.set_value(doctype, name, "module", module, update_modified=False)
		frappe.logger().info(f"av_tools: moved {doctype} {name} from module {stored_module} to {module}")
