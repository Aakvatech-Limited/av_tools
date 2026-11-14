"""Configurable 30-day monthly payroll proration for Frappe HRMS.

Uses the upstream attendance/leave calculation first. Never replaces HRMS
statutory deduction, loan or journal-entry logic.
"""

import calendar

import frappe
from frappe.utils import cint, flt, getdate


def fixed_30_payment_days(
    actual_payment_days,
    actual_working_days,
    start_date,
    end_date,
    actual_start_date,
    actual_end_date,
    mode="Deduction",
    crossover_days=15,
):
    """Calculate payable days with a fixed divisor of 30.

    Deduction: 30 minus equivalent unpaid/absent days for a complete month.
    Attendance: actual payable working days reported by HRMS.
    Automatic: Deduction until unpaid days reach crossover, then Attendance.
    Regardless of mode, a full month with zero payable days pays zero.
    For partial pay periods or eligibility, actual payable days are used.
    """
    actual_payment = flt(actual_payment_days)
    working = flt(actual_working_days)
    if actual_payment <= 0:
        return 0.0

    start = getdate(start_date)
    end = getdate(end_date)
    eligible_start = getdate(actual_start_date)
    eligible_end = getdate(actual_end_date)
    full_month = (
        start.year == end.year
        and start.month == end.month
        and start.day == 1
        and end.day == calendar.monthrange(end.year, end.month)[1]
        and eligible_start <= start
        and eligible_end >= end
    )

    if not full_month:
        return max(0.0, min(30.0, actual_payment))

    unpaid = max(0.0, working - actual_payment)
    if mode == "Automatic":
        mode = "Attendance" if unpaid >= flt(crossover_days) else "Deduction"

    if mode == "Attendance":
        payable = actual_payment
    elif mode == "Deduction":
        payable = 30.0 - unpaid
    else:
        raise ValueError("Unsupported fixed 30-day payroll proration mode")

    return max(0.0, min(30.0, payable))


class FixedThirtyDaySalarySlip:
    """Mixin registered via extend_doctype_class (HRMS v16)."""

    def get_working_days_details(self, lwp=None, for_preview=0, lwp_days_corrected=None):
        result = super().get_working_days_details(
            lwp=lwp, for_preview=for_preview, lwp_days_corrected=lwp_days_corrected
        )
        if (
            self.get("payroll_frequency") != "Monthly"
            or cint(self.get("salary_slip_based_on_timesheet"))
            or not frappe.get_meta("Payroll Settings").has_field("custom_fixed_30_day_month")
            or not cint(frappe.db.get_single_value("Payroll Settings", "custom_fixed_30_day_month"))
        ):
            return result

        if not all(self.get(field) for field in (
            "start_date", "end_date", "actual_start_date", "actual_end_date"
        )):
            return result

        settings = frappe.db.get_single_value
        mode = settings("Payroll Settings", "custom_fixed_30_proration_mode") or "Deduction"
        crossover = settings("Payroll Settings", "custom_fixed_30_crossover_days")
        self.payment_days = fixed_30_payment_days(
            self.payment_days,
            self.total_working_days,
            self.start_date,
            self.end_date,
            self.actual_start_date,
            self.actual_end_date,
            mode=mode,
            crossover_days=crossover if crossover is not None else 15,
        )
        self.total_working_days = 30
        return result
