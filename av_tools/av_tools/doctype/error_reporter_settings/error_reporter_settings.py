import base64
import hashlib
import time
import uuid

import frappe
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from frappe.model.document import Document
from frappe.utils import now_datetime


class ErrorReporterSettings(Document):
	pass


def _get_settings():
	return frappe.get_single("Error Reporter Settings")


def _ensure_identity(settings):
	changed = False
	if not settings.site_uuid:
		settings.site_uuid = str(uuid.uuid4())
		changed = True
	if not settings.site_name:
		settings.site_name = frappe.local.site
		changed = True
	if not settings.public_key or not settings.get_password("private_key", raise_exception=False):
		private_key = Ed25519PrivateKey.generate()
		private_pem = private_key.private_bytes(
			encoding=serialization.Encoding.PEM,
			format=serialization.PrivateFormat.PKCS8,
			encryption_algorithm=serialization.NoEncryption(),
		).decode("utf-8")
		public_pem = (
			private_key.public_key()
			.public_bytes(
				encoding=serialization.Encoding.PEM,
				format=serialization.PublicFormat.SubjectPublicKeyInfo,
			)
			.decode("utf-8")
		)
		settings.private_key = private_pem
		settings.public_key = public_pem
		changed = True
	if changed:
		settings.save(ignore_permissions=True)
	return settings


@frappe.whitelist()
def generate_identity():
	frappe.only_for("System Manager")
	settings = _ensure_identity(_get_settings())
	return {
		"site_uuid": settings.site_uuid,
		"site_name": settings.site_name,
		"public_key": settings.public_key,
	}


@frappe.whitelist()
def enroll_now():
	frappe.only_for("System Manager")
	settings = _ensure_identity(_get_settings())
	if not settings.central_server_url:
		frappe.throw("Central Server URL is required")

	url = (
		settings.central_server_url.rstrip("/")
		+ "/api/method/aakvatech_error_registry.api.enrollment.register"
	)
	payload = {
		"site_uuid": settings.site_uuid,
		"site_name": settings.site_name,
		"site_url": frappe.utils.get_url(),
		"public_key": settings.public_key,
		"frappe_version": getattr(frappe, "__version__", None),
		"erpnext_version": _get_app_version("erpnext"),
		"av_tools_version": _get_app_version("av_tools"),
	}
	response = requests.post(url, json=payload, timeout=30)
	settings.last_enrollment_attempt = now_datetime()
	response_data = response.json()
	result = response_data.get("message") if isinstance(response_data, dict) else response_data
	if not isinstance(result, dict):
		result = response_data

	if response.status_code in (200, 202):
		settings.enrollment_status = "Pending Approval"
	elif response.status_code == 403:
		status = result.get("status") if isinstance(result, dict) else None
		if status in ("Active", "Pending Approval", "Rejected"):
			settings.enrollment_status = status
	settings.save(ignore_permissions=True)
	if response.status_code not in (200, 202, 403):
		response.raise_for_status()
	return result


def sign_payload(body_bytes):
	settings = _ensure_identity(_get_settings())
	private_pem = settings.get_password("private_key")
	private_key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
	timestamp = str(int(time.time()))
	nonce = uuid.uuid4().hex
	body_hash = hashlib.sha256(body_bytes).hexdigest()
	message = (settings.site_uuid + "\n" + timestamp + "\n" + nonce + "\n" + body_hash).encode("utf-8")
	signature = base64.b64encode(private_key.sign(message)).decode("ascii")
	return {
		"X-Aakva-Site-ID": settings.site_uuid,
		"X-Aakva-Timestamp": timestamp,
		"X-Aakva-Nonce": nonce,
		"X-Aakva-Signature": signature,
		"Content-Type": "application/json",
	}


def _get_app_version(app_name):
	try:
		module = frappe.get_module(app_name)
		return getattr(module, "__version__", None)
	except Exception:
		return None
