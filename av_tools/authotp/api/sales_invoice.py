# Copyright (c) 2023, Aakvatech and contributors
# For license information, please see license.txt


import frappe
from frappe import _

def before_submit(doc, method):
    settings = frappe.get_single("AuthOTP Settings")
    if not settings:
        frappe.msgprint(_("Please configure AuthOTP Settings"), title=_("AuthOTP Settings"), indicator="red", alert=True)
        return
    
    is_authotp_applied = frappe.get_cached_value("Customer", doc.customer, "is_authotp_applied")
    otp_active = settings.get("active")
    if otp_active and is_authotp_applied and not doc.authotp_validated:
        frappe.throw(_("OTP not validated, please validated OTP first"))