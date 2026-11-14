"""Opt-in fixed-30-day monthly salary proration for Frappe HRMS.

Keep upstream attendance/leave logic intact; only adjust the ratio used for
payment-day dependent salary components. Other payroll frequencies and
timesheet-based wages retain upstream behavior.
"""

import calendar

import frappe
from frappe.utils import cint, flt, getdate


def fixed_30_payment_days(
    actual_payment_days, actual_working_days, start_date, end_date,
    actual_start_date, actual_end_date
):
    """Return payable days on a 30-day basis, preserving full monthly pay.

    Whole calendar months: 30 minus unpaid/absent days as evaluated by HRMS.
    Partial eligibility (joining, leaving, partial pay period): use actual
    eligible payable days / 30, capped at 30 for overlength months.
    """
    start = getdate(start_date)
    end = getdate(end_date)
    actual_start = getdate(actual_start_date)
    actual_end = getdate(actual_end_date)
    full_calendar_month = (
        start.year == end.year
        and start.month == end.month
        and start.day == 1
        and end.day == calendar.monthrange(end.year, end.month)[1]
    )
    full_eligibility = actual_start <= start and actual_end >= end
    if full_calendar_month and full_eligibility:
        unpaid_days = max(flt(actual_working_days) - flt(actual_payment_days), 0)
        return max(30.0 - unpaid_days, 0.0)
    return min(max(flt(actual_payment_days), 0.0), 30.0)


class FixedThirtyDaySalarySlip:
    """Mixin attached through extend_doctype_class, not an HRMS replacement."""

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

        if not all(
            self.get(field)
            for field in ("start_date", "end_date", "actual_start_date", "actual_end_date")
        ):
            return result

        original_working_days = flt(self.total_working_days)
        original_payment_days = flt(self.payment_days)
        self.payment_days = fixed_30_payment_days(
            original_payment_days,
            original_working_days,
            self.start_date,
            self.end_date,
            self.actual_start_date,
            self.actual_end_date,
        )
        self.total_working_days = 30
        return result
