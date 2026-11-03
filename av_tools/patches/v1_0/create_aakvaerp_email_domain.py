"""Create the default AakvaERP email domain without changing site-specific settings."""

import frappe


def execute():
	if frappe.db.exists("Email Domain", "aakvaerp.com"):
		return

	frappe.get_doc(
		{
			"doctype": "Email Domain",
			"domain_name": "aakvaerp.com",
			"email_server": "mail.aakvaerp.com",
			"use_imap": 1,
			"use_ssl": 1,
			"validate_ssl_certificate": 1,
			"use_starttls": 0,
			"incoming_port": "993",
			"attachment_limit": 25,
			"smtp_server": "mail.aakvaerp.com",
			"use_tls": 0,
			"use_ssl_for_outgoing": 1,
			"validate_ssl_certificate_for_outgoing": 1,
			"smtp_port": "465",
			"append_emails_to_sent_folder": 0,
			"sent_folder_name": "Sent",
		}
	).insert(ignore_permissions=True)
