import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PayrollDeductionProtectionPolicy(Document):
    def validate(self):
        if not 0 <= flt(self.protected_percentage) <= 100:
            frappe.throw(_("Protected Earnings Percentage must be between 0 and 100."))
        if flt(self.minimum_protected_amount) < 0:
            frappe.throw(_("Minimum Protected Amount cannot be negative."))
        if self.protection_basis == "Basic Salary Component" and not self.basic_salary_component:
            frappe.throw(_("Basic Salary Component is required for this basis."))
        seen = set()
        for rule in self.deduction_rules:
            if not rule.enabled:
                continue
            if rule.salary_component in seen:
                frappe.throw(_("Duplicate deduction component: {0}").format(rule.salary_component))
            seen.add(rule.salary_component)
            component = frappe.get_cached_doc("Salary Component", rule.salary_component)
            if component.type != "Deduction":
                frappe.throw(_("Only Deduction salary components may be configured: {0}").format(rule.salary_component))
            if component.get("variable_based_on_taxable_salary"):
                frappe.throw(_("Tax-derived deduction components cannot be deferred: {0}").format(rule.salary_component))
