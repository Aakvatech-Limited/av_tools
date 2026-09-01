import hashlib
import json
import os
import re
import subprocess

import frappe
import requests
from frappe.utils import add_days, getdate

from av_tools.av_tools.doctype.error_reporter_settings.error_reporter_settings import sign_payload
from av_tools.error_reporting.analyzer import analyze_error_log

SECRET_RE = re.compile(
	r"(?i)(password|passwd|api[_-]?key|api[_-]?secret|token|authorization|cookie|session)(\s*[:=]\s*)([^\s,;]+)"
)


def process_previous_day_errors():
	settings = frappe.get_single("Error Reporter Settings")
	if not settings.enabled or not settings.central_server_url:
		return

	report_date = add_days(getdate(), -1)
	payload = build_payload(report_date)
	if not payload["errors"]:
		return
	send_payload(payload)


def build_payload(report_date):
	start = str(report_date) + " 00:00:00"
	end = str(add_days(report_date, 1)) + " 00:00:00"
	logs = frappe.get_all(
		"Error Log",
		filters={"creation": ["between", [start, end]]},
		fields=["name", "creation", "error", "method"],
		order_by="creation asc",
	)

	grouped = {}
	for row in logs:
		observation = analyze_error_log(frappe._dict(row))
		if not observation:
			continue
		key = (
			observation["app_name"],
			observation["file_path"],
			observation.get("function_name"),
			observation.get("line_number"),
			observation["exception_type"],
		)
		if key not in grouped:
			observation["occurrence_count"] = 0
			observation["first_seen"] = row.creation
			observation["last_seen"] = row.creation
			observation["app_version"] = _get_app_version(observation["app_name"])
			observation["git_commit_sha"] = _get_git_sha(observation["app_name"])
			observation["representative_traceback"] = _sanitize(observation.get("representative_traceback"))
			observation["source_context"] = _sanitize(observation.get("source_context"))
			grouped[key] = observation
		current = grouped[key]
		current["occurrence_count"] += 1
		current["last_seen"] = row.creation
		current["latest_local_error_log"] = row.name

	settings = frappe.get_single("Error Reporter Settings")
	batch_id = settings.site_uuid + ":" + str(report_date)
	return {"batch_id": batch_id, "reporting_date": str(report_date), "errors": list(grouped.values())}


def send_payload(payload):
	settings = frappe.get_single("Error Reporter Settings")
	if settings.enrollment_status not in ("Active", "Pending Approval"):
		frappe.log_error("Error Reporter site is not enrolled or active", "Error Registry Reporter")
		return

	body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
	headers = sign_payload(body)
	url = (
		settings.central_server_url.rstrip("/")
		+ "/api/method/aakvatech_error_registry.api.intake.report_errors"
	)
	response = requests.post(url, data=body, headers=headers, timeout=60)

	if response.status_code == 403:
		settings.enrollment_status = "Pending Approval"
		settings.save(ignore_permissions=True)
		return
	response.raise_for_status()
	settings.enrollment_status = "Active"
	settings.last_successful_report = payload["reporting_date"]
	settings.last_batch_id = payload["batch_id"]
	settings.save(ignore_permissions=True)
	return response.json()


@frappe.whitelist()
def send_yesterday_now():
	frappe.only_for("System Manager")
	report_date = add_days(getdate(), -1)
	payload = build_payload(report_date)
	if not payload["errors"]:
		return {"accepted": True, "message": "No reportable Error Logs found", "errors": 0}
	return send_payload(payload)


def _get_app_version(app_name):
	try:
		module = frappe.get_module(app_name)
		return getattr(module, "__version__", None)
	except Exception:
		return None


def _get_git_sha(app_name):
	try:
		app_path = os.path.join(frappe.utils.get_bench_path(), "apps", app_name)
		return subprocess.check_output(
			["git", "-C", app_path, "rev-parse", "HEAD"], text=True, timeout=5
		).strip()
	except Exception:
		return None


def _sanitize(value):
	if not value:
		return value
	return SECRET_RE.sub(lambda match: match.group(1) + match.group(2) + "<redacted>", value)
