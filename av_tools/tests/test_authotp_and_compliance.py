# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

from unittest.mock import patch

import frappe
import pyotp
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from av_tools.authotp.api.sales_invoice import before_submit
from av_tools.authotp.doctype.otp_register.otp_register import register_otp, validate_doc_otp, validate_otp
from av_tools.compliance.doctype.license_register.license_register import update_license_statuses

COMPANY = "_Test Company"


class TestOtpRegister(IntegrationTestCase):
	def make_register(self, otp_type="OTP APP", party_type="Customer", party="_Test Customer"):
		return frappe.get_doc(
			{"doctype": "OTP Register", "party_type": party_type, "party": party, "otp_type": otp_type}
		).insert()

	def test_insert_generates_secret_and_party_name(self):
		register = self.make_register()
		self.assertEqual(register.registered, 0)
		self.assertEqual(
			register.party_name, frappe.db.get_value("Customer", "_Test Customer", "customer_name")
		)
		self.assertEqual(register.user_name, register.party_name)
		self.assertEqual(len(register.get_otp_secret()), 32)
		user_register = self.make_register(party_type="User", party="Administrator")
		self.assertEqual(user_register.party_name, "Administrator")

	def test_register_and_validate_totp(self):
		frappe.db.set_single_value("AuthOTP Settings", "otp_issuer_name", "AV Test")
		register = self.make_register()
		link = register_otp(register.as_dict())
		self.assertIn("api.qrserver.com", link)
		self.assertIn("AV%20Test", link)

		self.assertRaises(frappe.ValidationError, validate_otp, register.as_dict(), "000000")
		code = pyotp.TOTP(register.get_otp_secret()).now()
		self.assertTrue(validate_otp(register.as_dict(), code, submit=True))
		register.reload()
		self.assertEqual(register.registered, 1)
		self.assertEqual(register.docstatus, 1)
		self.assertRaises(frappe.ValidationError, register_otp, register.as_dict())
		self.assertTrue(validate_doc_otp(register.name, pyotp.TOTP(register.get_otp_secret()).now()))
		self.assertRaises(frappe.ValidationError, validate_doc_otp, register.name, "000000")

	def test_submit_requires_registration_and_other_channels_not_implemented(self):
		register = self.make_register()
		self.assertRaises(frappe.ValidationError, register.submit)
		for otp_type in ("SMS", "Email"):
			self.assertRaises(
				frappe.ValidationError, register_otp, self.make_register(otp_type=otp_type).as_dict()
			)

	def test_sales_invoice_before_submit_gate(self):
		invoice = frappe.new_doc("Sales Invoice")
		invoice.customer = "_Test Customer"
		invoice.authotp_validated = 0
		frappe.db.set_value("Customer", "_Test Customer", "is_authotp_applied", 1)
		frappe.clear_cache(doctype="Customer")
		frappe.db.set_single_value("AuthOTP Settings", "active", 1)
		self.assertRaises(frappe.ValidationError, before_submit, invoice, "before_submit")
		invoice.authotp_validated = 1
		self.assertIsNone(before_submit(invoice, "before_submit"))
		frappe.db.set_single_value("AuthOTP Settings", "active", 0)
		invoice.authotp_validated = 0
		self.assertIsNone(before_submit(invoice, "before_submit"))


class TestCompliance(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("License Type", "AV Test Licence"):
			frappe.get_doc({"doctype": "License Type", "__newname": "AV Test Licence"}).insert()

	def make_license(self, **values):
		doc = frappe.get_doc(
			{
				"doctype": "License Register",
				"naming_series": "LIC-.YYYY.-.#####",
				"license_type": "AV Test Licence",
				"license_name": "AV Test",
				"license_number": frappe.generate_hash(length=6),
				"issuing_authority": "TRA",
				"issue_date": add_days(nowdate(), -100),
				"expiry_date": add_days(nowdate(), 100),
				"company": COMPANY,
				**values,
			}
		)
		return doc.insert()

	def test_status_follows_expiry(self):
		self.assertEqual(self.make_license().status, "Active")
		self.assertEqual(self.make_license(expiry_date=add_days(nowdate(), -1)).status, "Expired")
		self.assertEqual(
			self.make_license(expiry_date=add_days(nowdate(), 5), reminder_days_before=10).status,
			"Pending Renewal",
		)
		self.assertEqual(
			self.make_license(status="Suspended", expiry_date=add_days(nowdate(), -1)).status, "Suspended"
		)
		self.assertRaises(
			frappe.ValidationError,
			self.make_license,
			issue_date=nowdate(),
			expiry_date=add_days(nowdate(), -1),
		)

	def test_scheduler_updates_statuses_and_notifies(self):
		lic = self.make_license(reminder_days_before=10, notify_role="System Manager")
		frappe.db.set_value("License Register", lic.name, {"expiry_date": add_days(nowdate(), 3)})
		with patch(
			"av_tools.compliance.doctype.license_register.license_register.enqueue_create_notification"
		) as notify:
			update_license_statuses()
		self.assertEqual(frappe.db.get_value("License Register", lic.name, "status"), "Pending Renewal")
		notify.assert_called_once()
		frappe.db.set_value("License Register", lic.name, {"expiry_date": add_days(nowdate(), -3)})
		with patch(
			"av_tools.compliance.doctype.license_register.license_register.enqueue_create_notification"
		) as notify:
			update_license_statuses()
		self.assertEqual(frappe.db.get_value("License Register", lic.name, "status"), "Expired")
		self.assertEqual(notify.call_args[0][1]["type"], "Alert")

	def test_inspection_record_and_type(self):
		if not frappe.db.exists("Inspection Type", "AV Test Inspection"):
			frappe.get_doc({"doctype": "Inspection Type", "__newname": "AV Test Inspection"}).insert()
		meta = frappe.get_meta("Inspection Record")
		doc = frappe.new_doc("Inspection Record")
		for df in meta.fields:
			if df.reqd and not doc.get(df.fieldname):
				if df.fieldtype == "Link" and df.options == "Inspection Type":
					doc.set(df.fieldname, "AV Test Inspection")
				elif df.fieldtype == "Link" and df.options == "Company":
					doc.set(df.fieldname, COMPANY)
				elif df.fieldtype == "Date":
					doc.set(df.fieldname, nowdate())
				elif df.fieldtype == "Select":
					doc.set(df.fieldname, next(o for o in df.options.split("\n") if o))
				elif df.fieldtype in ("Data", "Small Text", "Text", "Text Editor"):
					doc.set(df.fieldname, "AV Test")
		doc.insert()
		self.assertTrue(doc.name)
