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


def get_declared_modules(app=APP_NAME):
	"""Map every Report and Print Format the app ships to the module its file declares."""
	declared = {}
	for module in frappe.get_module_list(app):
		for doctype in OWNED_DOCTYPES:
			folder = frappe.get_app_path(app, frappe.scrub(module), frappe.scrub(doctype))
			if not os.path.isdir(folder):
				continue

			for slug in os.listdir(folder):
				definition = read_definition(folder, slug)
				if definition:
					declared[(doctype, definition["name"])] = definition["module"]

	return declared


def get_records_shipped_by_other_apps():
	"""Records another installed app also ships, so av_tools must not claim them."""
	shared = set()
	for app in frappe.get_installed_apps():
		if app != APP_NAME:
			shared.update(get_declared_modules(app))

	return shared


def get_stale_records():
	"""Records only av_tools ships whose stored module differs from the one their file declares."""
	shared = get_records_shipped_by_other_apps()
	stale = []

	for (doctype, name), module in get_declared_modules().items():
		if (doctype, name) in shared:
			continue

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

	Records another installed app still ships are left alone. csf_tz keeps its own copy of
	several salary and permission reports, and claiming those would swap the implementation
	underneath it.
	"""
	for doctype, name, stored_module, module in get_stale_records():
		frappe.db.set_value(doctype, name, "module", module, update_modified=False)
		frappe.logger().info(f"av_tools: moved {doctype} {name} from module {stored_module} to {module}")
