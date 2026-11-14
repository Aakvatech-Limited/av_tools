"""Opt-in wage deduction protection and auditable recovery for HRMS v16.

Only explicitly whitelisted *ordinary* salary deduction rows are deferrable.
PAYE, statutory components, additional salaries, and Lending loan repayments
are deliberately outside automated deferral.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

POLICY = "Payroll Deduction Protection Policy"
LEDGER = "Payroll Deduction Recovery Entry"
PLAN_FIELD = "custom_deduction_recovery_plan"


def allocate_capacity(gross, mandatory, protected, current, arrears):
    """Pure current-first allocation. Return (current, arrears) allocations.

    Monetary rounding is performed at the currency precision by caller.
    """
    capacity = max(0, flt(gross) - flt(mandatory) - flt(protected))
    current_paid = []
    for amount in current:
        paid = min(capacity, max(0, flt(amount)))
        current_paid.append(paid)
        capacity -= paid
    old_paid = []
    for amount in arrears:
        paid = min(capacity, max(0, flt(amount)))
        old_paid.append(paid)
        capacity -= paid
    return current_paid, old_paid


def policy_for(company):
    name = frappe.db.get_value(POLICY, {"company": company, "enabled": 1}, "name")
    return frappe.get_cached_doc(POLICY, name) if name else None


def get_open_arrears(employee, company, component):
    """FIFO amounts net of submitted recovery entries, never draft transactions."""
    deferred = frappe.get_all(
        LEDGER,
        filters={
            "employee": employee, "company": company,
            "salary_component": component, "entry_type": "Deferred", "docstatus": 1
        },
        fields=["name", "amount", "posting_date"],
        order_by="posting_date asc, creation asc, name asc",
    )
    if not deferred:
        return []
    recovered = frappe.get_all(
        LEDGER,
        filters={
            "employee": employee, "company": company,
            "salary_component": component, "entry_type": "Recovered", "docstatus": 1,
            "arrear_reference": ["in", [d.name for d in deferred]],
        },
        fields=["arrear_reference", "amount"],
    )
    sums = {}
    for entry in recovered:
        sums[entry.arrear_reference] = sums.get(entry.arrear_reference, 0) + flt(entry.amount)
    return [
        {"arrear_reference": d.name, "amount": flt(d.amount) - sums.get(d.name, 0)}
        for d in deferred if flt(d.amount) - sums.get(d.name, 0) > 0.001
    ]


def build_plan(slip, policy):
    if not policy:
        return None
    if slip.get("salary_slip_based_on_timesheet"):
        return None

    rules = sorted(
        [r for r in policy.get("deduction_rules") if cint(r.enabled)],
        key=lambda r: (cint(r.priority), r.salary_component),
    )
    if not rules:
        return None

    by_component = {r.salary_component: r for r in rules}
    if len(by_component) != len(rules):
        frappe.throw(_("Duplicate Salary Component in deduction protection policy."))

    rows = {}
    mandatory = flt(slip.get("total_loan_repayment"))
    for row in slip.get("deductions", []):
        amount = max(0, flt(row.amount))
        component = row.salary_component
        if component in by_component:
            if row.get("additional_salary") or row.get("variable_based_on_taxable_salary"):
                frappe.throw(_("Component {0} cannot be deferred because it is additional salary or variable tax.").format(component))
            if component in rows:
                frappe.throw(_("Duplicate recoverable deduction component {0} on salary slip.").format(component))
            rows[component] = {"row": row, "amount": amount}
        else:
            mandatory += amount

    gross = flt(slip.gross_pay)
    base = gross
    if policy.protection_basis == "Basic Salary Component":
        basic_component = policy.basic_salary_component
        matching = [r for r in slip.get("earnings", []) if r.salary_component == basic_component]
        if len(matching) != 1:
            frappe.throw(_("Protected earnings base component {0} must exist once in earnings.").format(basic_component))
        base = flt(matching[0].amount)

    protected = max(
        flt(policy.minimum_protected_amount),
        base * flt(policy.protected_percentage) / 100,
    )
    protected = flt(protected, 2)
    if gross - mandatory < protected - 0.01:
        frappe.throw(_(
            "Mandatory deductions (including Lending repayments) leave less than the protected earnings amount. "
            "Resolve statutory and loan deductions before submitting Salary Slip."
        ))

    current = []
    for rule in rules:
        if rule.salary_component in rows:
            current.append((rule.salary_component, rows[rule.salary_component]["amount"]))

    old = []
    for rule in rules:
        for balance in get_open_arrears(slip.employee, slip.company, rule.salary_component):
            old.append((rule.salary_component, balance["arrear_reference"], balance["amount"]))

    paid_current, paid_old = allocate_capacity(
        gross, mandatory, protected,
        [amount for _, amount in current],
        [amount for _, _, amount in old],
    )

    detail = {"current": [], "prior": [], "policy": policy.name}
    for (component, scheduled), paid in zip(current, paid_current):
        paid = flt(paid, 2)
        deferred = flt(max(0, scheduled - paid), 2)
        if deferred:
            detail["current"].append({"component": component, "scheduled": scheduled, "paid": paid, "deferred": deferred})
        rows[component]["row"].amount = paid

    for (component, reference, _), paid in zip(old, paid_old):
        paid = flt(paid, 2)
        if not paid:
            continue
        detail["prior"].append({"component": component, "arrear_reference": reference, "recovered": paid})
        if component in rows:
            rows[component]["row"].amount = flt(rows[component]["row"].amount + paid, 2)
        else:
            slip.append("deductions", {
                "salary_component": component,
                "amount": paid,
                "default_amount": 0,
                "depends_on_payment_days": 0,
            })
    return detail


def make_entries(slip):
    if not frappe.get_meta("Salary Slip").has_field(PLAN_FIELD):
        return
    raw = slip.get(PLAN_FIELD)
    if not raw:
        return
    plan = json.loads(raw)
    if not plan.get("policy"):
        return
    if frappe.db.exists(LEDGER, {"salary_slip": slip.name, "docstatus": 1}):
        frappe.throw(_("Deduction recovery entries already exist for Salary Slip {0}").format(slip.name))
    for d in plan["current"]:
        if flt(d["deferred"]) > 0:
            entry = frappe.get_doc({
                "doctype": LEDGER, "employee": slip.employee, "company": slip.company,
                "salary_slip": slip.name, "posting_date": slip.end_date,
                "salary_component": d["component"], "entry_type": "Deferred",
                "amount": d["deferred"],
            })
            entry.insert(ignore_permissions=True)
            entry.submit()
    for d in plan["prior"]:
        if flt(d["recovered"]) > 0:
            entry = frappe.get_doc({
                "doctype": LEDGER, "employee": slip.employee, "company": slip.company,
                "salary_slip": slip.name, "posting_date": slip.end_date,
                "salary_component": d["component"], "entry_type": "Recovered",
                "arrear_reference": d["arrear_reference"], "amount": d["recovered"],
            })
            entry.insert(ignore_permissions=True)
            entry.submit()


def cancel_entries(slip):
    entries = frappe.get_all(
        LEDGER, filters={"salary_slip": slip.name, "docstatus": 1}, pluck="name"
    )
    for name in entries:
        # Prevent cancelling the original liability while subsequent months
        # still contain submitted recoveries against it.
        dependent = frappe.db.exists(LEDGER, {
            "arrear_reference": name, "entry_type": "Recovered", "docstatus": 1
        })
        if dependent:
            frappe.throw(_("Cancel later Salary Slips that recovered arrears from {0} first.").format(name))
    for name in entries:
        frappe.get_doc(LEDGER, name).cancel()


class ProtectedSalarySlip:
    """Cooperative v16 extension: leave upstream payroll and tax logic intact."""

    def set_net_pay(self):
        policy = policy_for(self.company) if self.company and self.employee else None
        if not policy or not frappe.get_meta("Salary Slip").has_field(PLAN_FIELD):
            return super().set_net_pay()
        # On repeated form calculations HRMS rebuilds deductions, but protect
        # against calling set_net_pay twice on unchanged in-memory rows.
        if getattr(self, "_av_protection_applied", False):
            return super().set_net_pay()
        plan = build_plan(self, policy)
        self.set(PLAN_FIELD, json.dumps(plan or {}))
        self._av_protection_applied = True
        return super().set_net_pay()

    def on_submit(self):
        super().on_submit()
        if self.get(PLAN_FIELD):
            make_entries(self)

    def on_cancel(self):
        cancel_entries(self)
        return super().on_cancel()
