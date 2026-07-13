import frappe
from frappe.utils import add_days, today, format_date

def check_missing_employee_checkins():
    """
    Checks if active employees missed checking in yesterday.
    Sends an email alert to all active System Managers if any are missing.
    """
    if not frappe.db.get_single_value("AV Tools Settings", "enable_missing_employee_checkin_alert"):
        return

    # 1. Get yesterday's date
    yesterday = add_days(today(), -1)
    start_of_yesterday = f"{yesterday} 00:00:00"
    end_of_yesterday = f"{yesterday} 23:59:59"

    # 2. Fetch all unique employee IDs who DID check in yesterday
    checked_in_ids = frappe.get_all(
        "Employee Checkin",
        filters={"time": ["between", [start_of_yesterday, end_of_yesterday]]},
        pluck="employee"
    )
    # Filter unique IDs
    checked_in_ids = list(set(checked_in_ids))

    # 3. Fetch all Active employees
    active_employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name"]
    )

    # 4. Filter out employees who have NO check-ins
    missing_employees = [
        emp for emp in active_employees if emp.name not in checked_in_ids
    ]

    # If everyone checked in, stop here
    if not missing_employees:
        return

    # 5. Compile a generic alert message (no employee names/IDs)
    formatted_date = format_date(yesterday)
    message = f"<h3>Missing Employee Check-ins Alert</h3>"
    message += f"<p>Some active employees have no check-in records for <b>{formatted_date}</b>. Please check and verify.</p>"

    # 6. Fetch all enabled User emails assigned to the 'System Manager' role
    system_managers = frappe.get_all("Has Role", filters={"role": "System Manager"}, pluck="parent")
    recipients = frappe.get_all("User", filters={"name": ["in", system_managers], "enabled": 1}, pluck="email")

    # 7. Send the email notification
    if recipients:
        frappe.sendmail(
            recipients=recipients,
            subject=f"Notification: Missing Check-ins for {formatted_date}",
            message=message,
        )