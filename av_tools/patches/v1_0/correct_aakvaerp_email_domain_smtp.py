"""Correct the legacy AakvaERP SMTP defaults without overwriting site customizations."""

import frappe

from av_tools.patches.v1_0.create_aakvaerp_email_domain import execute as create_domain


def execute():
	if not frappe.db.exists("Email Domain", "aakvaerp.com"):
		create_domain()
		return

	domain = frappe.get_doc("Email Domain", "aakvaerp.com")
	# Only update the exact SMTP transport settings shipped by the original patch.
	if (
		int(domain.smtp_port or 0) != 465
		or int(domain.use_tls or 0) != 0
		or int(domain.use_ssl_for_outgoing or 0) != 1
		or domain.smtp_server != "mail.aakvaerp.com"
	):
		return

	domain.smtp_port = 587
	domain.use_tls = 1
	domain.use_ssl_for_outgoing = 0
	domain.save(ignore_permissions=True)
