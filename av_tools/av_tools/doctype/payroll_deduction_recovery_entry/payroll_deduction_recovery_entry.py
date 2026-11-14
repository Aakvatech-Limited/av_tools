import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PayrollDeductionRecoveryEntry(Document):
    def validate(self):
        if flt(self.amount) <= 0:
            frappe.throw(_("Recovery entry amount must be greater than zero."))
        if self.entry_type == "Recovered":
            if not self.arrear_reference:
                frappe.throw(_("Recovered entries require an original deferred entry."))
            deferred = frappe.get_doc(self.doctype, self.arrear_reference)
            if deferred.entry_type != "Deferred" or deferred.docstatus != 1:
                frappe.throw(_("Original entry must be a submitted deferral."))
            if (deferred.employee, deferred.company, deferred.salary_component) != (
                self.employee, self.company, self.salary_component
            ):
                frappe.throw(_("Recovery entry must match employee, company, and salary component."))
            if deferred.salary_slip == self.salary_slip:
                frappe.throw(_("Cannot recover arrears from the same Salary Slip."))
        elif self.arrear_reference:
            frappe.throw(_("Deferred entries cannot reference another recovery entry."))
