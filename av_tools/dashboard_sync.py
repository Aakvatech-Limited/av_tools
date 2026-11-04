"""Restore app-owned standard dashboard records not imported by module sync.

This routine creates missing Dashboard, Dashboard Chart, and Number Card records
without replacing site-specific edits to existing records.
"""

import json
from pathlib import Path

import frappe
from frappe.modules.import_file import import_file_by_path

STANDARD_ASSETS = (
	("Number Card", "number_card"),
	("Dashboard Chart", "dashboard_chart"),
	("Dashboard", "dashboard"),
)


def execute():
	for module in ("av_tools", "selling_pricing_engine"):
		sync_module(module)
	validate_dashboard("Manufacturing BOM Variance")
	validate_dashboard("Sales Manager Pricing")


def sync_module(module):
	module_path = Path(frappe.get_app_path("av_tools", module))

	for doctype, directory in STANDARD_ASSETS:
		root = module_path / directory
		if not root.is_dir():
			continue

		for folder in sorted(root.iterdir()):
			if not folder.is_dir():
				continue
			path = folder / (folder.name + ".json")
			if not path.is_file():
				continue

			# Only import missing records. Existing site customizations are
			# retained; do not use force to overwrite them during every migrate.
			with path.open(encoding="utf-8") as source:
				data = json.load(source)

			if data.get("doctype") != doctype or not data.get("is_standard"):
				continue

			name = data.get("name")
			if not name:
				frappe.throw("Missing name in standard asset: " + str(path))

			if not frappe.db.exists(doctype, name):
				import_file_by_path(str(path), force=True, ignore_version=True)
				if not frappe.db.exists(doctype, name):
					frappe.throw("Could not synchronize " + doctype + ": " + name)


def validate_dashboard(name):
	# Fail loudly rather than leave a dashboard with missing dependencies.
	if frappe.db.exists("Dashboard", name):
		dashboard = frappe.get_doc("Dashboard", name)
		for card in dashboard.cards:
			if not frappe.db.exists("Number Card", card.card):
				frappe.throw("Missing Number Card for " + name + ": " + card.card)
		for chart in dashboard.charts:
			if not frappe.db.exists("Dashboard Chart", chart.chart):
				frappe.throw("Missing Dashboard Chart for " + name + ": " + chart.chart)
