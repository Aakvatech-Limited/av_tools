"""Adopt the site prototype without recreating records or leaving duplicate hooks."""

import json
from pathlib import Path

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

RUN_DOCTYPE = "Bank Transaction GL Generation"
REPORT = "Bank Transaction Statement"
SERVER_SCRIPTS = (
	"Bank Transaction GL Generation - Validate Request",
	"Bank Transaction GL Generation - Worker",
	"Bank Transaction GL Generation - Queue",
	"Bank Transaction - Validate GL Source",
	"Bank Transaction - Release GL Source on Cancel",
	"Bank Transaction - Release GL Source on Discard",
	"Bank Transaction - Require Live GL Generation",
)
CLIENT_SCRIPTS = (
	"Bank Transaction - Generate from GL Entries",
	"Bank Transaction GL Generation - Progress",
)


def prepare_site():
	"""Run before model sync, including when installing over the custom prototype."""
	if frappe.db.exists("DocType", RUN_DOCTYPE):
		if frappe.db.get_value("DocType", RUN_DOCTYPE, "custom"):
			# Do not orphan a queued legacy API call by disabling its Server Script.
			for run in frappe.get_all(
				RUN_DOCTYPE, filters={"status": ["in", ["Queued", "Running"]]}, fields=["name"]
			):
				jobs = frappe.get_all(
					"RQ Job",
					filters={"job_name": "GL Bank Transaction Generation " + run.name},
					order_by="creation desc",
					limit_page_length=1,
				)
				if not jobs or jobs[0].status in ("queued", "started", "deferred", "scheduled"):
					frappe.throw(
						_("Finish GL generation run {0} before migrating the prototype.").format(run.name)
					)
				frappe.db.set_value(RUN_DOCTYPE, run.name, "status", "Failed")
			frappe.db.set_value(
				"DocType", RUN_DOCTYPE, {"custom": 0, "module": "Av Tools"}, update_modified=False
			)
			frappe.clear_cache(doctype=RUN_DOCTYPE)
	if frappe.db.exists("Report", REPORT):
		frappe.db.set_value(
			"Report", REPORT, {"is_standard": "Yes", "module": "Av Tools"}, update_modified=False
		)


def after_migrate():
	"""Idempotent setup for new sites and sites with the original custom records."""
	path = Path(
		frappe.get_app_path(
			"av_tools",
			"patches",
			"custom_fields",
			"custom_fields_json",
			"bank_transaction_gl_generation.json",
		)
	)
	fields = json.loads(path.read_text())
	create_custom_fields(
		{"Bank Transaction": [{k: v for k, v in f.items() if k != "dt"} for f in fields]}, update=True
	)
	frappe.reload_doc("av_tools", "doctype", "bank_transaction_gl_generation", force=True)
	frappe.reload_doc("av_tools", "report", "bank_transaction_statement", force=True)
	# Keep the scripts for audit/reference, but do not execute both implementations.
	for doctype, names, field, value in (
		("Server Script", SERVER_SCRIPTS, "disabled", 1),
		("Client Script", CLIENT_SCRIPTS, "enabled", 0),
	):
		for name in names:
			if frappe.db.exists(doctype, name):
				frappe.db.set_value(doctype, name, field, value, update_modified=False)
	frappe.db.set_value("Report", REPORT, {"report_script": None, "javascript": None}, update_modified=False)
	frappe.clear_cache(doctype=RUN_DOCTYPE)
	frappe.clear_cache(doctype="Bank Transaction")
	frappe.clear_cache(doctype="Server Script")
	frappe.client_cache.delete_value("server_script_map")
	frappe.clear_cache(doctype="Client Script")
