# Copyright (c) 2023, Aakvatech and contributors
# For license information, please see license.txt


import pyotp
import frappe
from frappe import _
from frappe.model.document import Document


class OTPRegister(Document):
    def before_insert(self):
        self.registered = 0
        self.set_otp_secret()

    def validate(self):
        self.set_party_name()

    def on_submit(self):
        if not self.registered:
            frappe.throw(_("OTP not registered, please register OTP first"))

    def set_party_name(self):
        if not self.party:
            return
        if self.party_type == "Customer":
            self.party_name = frappe.get_cached_value(
                "Customer", self.party, "customer_name"
            )
        elif self.party_type == "Supplier":
            self.party_name = frappe.get_cached_value(
                "Supplier", self.party, "supplier_name"
            )
        elif self.party_type == "Employee":
            self.party_name = frappe.get_cached_value(
                "Employee", self.party, "employee_name"
            )
        elif self.party_type == "User":
            self.party_name = frappe.get_cached_value("User", self.party, "full_name")
        elif self.party_type == "Contact":
            self.party_name = frappe.get_cached_value(
                "Contact", self.party, "first_name"
            )
        elif self.party_type == "Lead":
            self.party_name = frappe.get_cached_value("Lead", self.party, "lead_name")
        elif self.party_type == "Sales Partner":
            self.party_name = self.party
        elif self.party_type == "Student":
            first_name, middle_name, last_name = frappe.get_cached_value(
                "Student", self.party, ["first_name", "middle_name", "last_name"]
            )
            self.party_name = " ".join(
                filter(None, [first_name, middle_name, last_name])
            )
        elif self.party_type == "Guardian":
            self.party_name = frappe.get_cached_value(
                "Guardian", self.party, "guardian_name"
            )
        elif self.party_type == "Donor":
            self.party_name = frappe.get_cached_value("Donor", self.party, "donor_name")
        elif self.party_type == "Member":
            self.party_name = frappe.get_cached_value(
                "Member", self.party, "member_name"
            )
        elif self.party_type == "Patient":
            self.party_name = frappe.get_cached_value(
                "Patient", self.party, "patient_name"
            )
        elif self.party_type == "Instructor":
            self.party_name = frappe.get_cached_value(
                "Instructor", self.party, "instructor_name"
            )
        elif self.party_type == "Sales Person":
            self.party_name = frappe.get_cached_value(
                "Sales Person", self.party, "sales_person_name"
            )
        elif self.party_type == "Teacher":
            self.party_name = frappe.get_cached_value(
                "Teacher", self.party, "teacher_name"
            )
        elif self.party_type == "Tenant":
            self.party_name = frappe.get_cached_value(
                "Tenant", self.party, "tenant_name"
            )
        elif self.party_type == "Visitor":
            self.party_name = frappe.get_cached_value(
                "Visitor", self.party, "visitor_name"
            )

        if not self.party_name:
            self.party_name = self.party

        if not self.user_name:
            self.user_name = self.party_name

    def set_otp_secret(self):
        self.otp_secret = pyotp.random_base32()

    def get_otp_secret(self):
        return self.get_password("otp_secret")


@frappe.whitelist()
def register_otp(otp_doc):
    otp_doc = frappe._dict(frappe.parse_json(otp_doc))
    otp_doc = frappe.get_doc(otp_doc)
    if otp_doc.docstatus == 1:
        frappe.throw(_("Document is already submitted"))
    if otp_doc.registered:
        frappe.throw(_("OTP already registered"))
    if otp_doc.otp_type == "OTP APP":
        return register_otp_app(otp_doc)
    elif otp_doc.otp_type == "SMS":
        return register_otp_sms(otp_doc)
    elif otp_doc.otp_type == "Email":
        return register_otp_email(otp_doc)


def register_otp_sms(otp_doc=None):
    frappe.throw(_("SMS OTP not implemented"))
    return


def register_otp_email(otp_doc=None):
    frappe.throw(_("Email OTP not implemented"))
    return


def register_otp_app(otp_doc):
    issuer_name = frappe.get_cached_value("AuthOTP Settings", "AuthOTP Settings", "otp_issuer_name")
    uri = pyotp.totp.TOTP(otp_doc.get_otp_secret()).provisioning_uri(name= f"( {otp_doc.user_name} )", issuer_name=issuer_name)
    qr_link = f"https://api.qrserver.com/v1/create-qr-code/?data={uri}&size=220x220&margin=0"
    return qr_link


@frappe.whitelist()
def validate_otp(otp_doc, otp_code, submit=False):
    otp_doc = frappe._dict(frappe.parse_json(otp_doc))
    otp_doc = frappe.get_doc(otp_doc)
    totp = pyotp.TOTP(otp_doc.get_otp_secret())
    if totp.verify(otp_code):
        otp_doc.registered = 1
        otp_doc.save()
        if submit:
            otp_doc.submit()
        frappe.msgprint(_("OTP Registered successfully"), alert=True)
        return True
    else:
        frappe.throw(_("Invalid OTP Code"))


@frappe.whitelist()
def validate_doc_otp(otp_register_name, otp_code):
    otp_doc = frappe.get_cached_doc("OTP Register", otp_register_name)
    totp = pyotp.TOTP(otp_doc.get_otp_secret())
    if totp.verify(otp_code):
        return True
    else:
        frappe.throw(_("Invalid OTP Code"))