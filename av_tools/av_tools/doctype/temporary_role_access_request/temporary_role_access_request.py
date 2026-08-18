# Copyright (c) 2025, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime, flt


class TemporaryRoleAccessRequest(Document):
    def before_insert(self):
        """Set defaults before insert."""
        if not self.requested_by:
            self.requested_by = frappe.session.user
        self.status = "Draft"

    def on_update(self):
        """Detect status changes and send notifications."""
        # Get the document state before this save
        doc_before_save = self.get_doc_before_save()

        if doc_before_save:
            old_status = doc_before_save.get("status")
            # Notify approvers when status changes to 'Pending Approval'
            if old_status == "Draft" and self.status == "Pending Approval":
                self._notify_approvers_of_new_request()

    def validate(self):
        """Main validation logic."""
        self._validate_requested_for_user()
        self._validate_role_requested()
        self._validate_dates()
        self._validate_no_overlapping_requests()
        self._validate_user_does_not_already_have_role()
        self._calculate_duration()

    def before_submit(self):
        """Run before submit (docstatus 0→1).
        This is triggered by Workflow when transitioning to Approved state."""
        # Set the approver
        self.approver = frappe.session.user

    def before_update_after_submit(self):
        """Called when workflow updates after submit (e.g., from Approved to Active/Expired)."""
        pass

    def on_submit(self):
        """Handle role granting when request is approved (docstatus=1).
        
        If from_datetime has already passed, activate immediately.
        Otherwise, the scheduler will activate it when from_datetime arrives.
        """
        now = now_datetime()
        from_dt = get_datetime(self.from_datetime)

        if from_dt <= now:
            self._grant_role()
        else:
            self.db_set("status", "Approved")

    def on_cancel(self):
        """Handle cancellation - revoke role if currently granted.

        Note: The workflow sets self.status to 'Cancelled' before calling
        on_cancel, so we check role_granted (a separate field) instead.
        Notification is sent inside _revoke_role().
        """
        if self.role_granted:
            self._revoke_role(reason="cancelled")
        self.db_set("status", "Cancelled")

    def before_cancel(self):
        """Validate before cancellation.

        Note: At this point, the workflow has already updated self.status to
        the target state's value, so we check the DB state instead."""
        doc_before = self.get_doc_before_save()
        if doc_before:
            old_status = doc_before.get("status")
            allowed_statuses = ("Pending Approval", "Approved", "Active")
            if old_status not in allowed_statuses:
                frappe.throw(
                    _("Only requests with status: {0} can be cancelled").format(
                        ", ".join(allowed_statuses)
                    )
                )

    # ---------- Validation Methods ----------

    def _validate_requested_for_user(self):
        """Ensure requested_for is an enabled user."""
        user_enabled = frappe.db.get_value("User", self.requested_for, "enabled")
        if user_enabled == 0:
            frappe.throw(
                _("User {0} is disabled. Please select an enabled user.").format(
                    frappe.bold(self.requested_for)
                )
            )

    def _validate_role_requested(self):
        """Ensure the role exists and is a valid role."""
        if not frappe.db.exists("Role", self.role_requested):
            frappe.throw(
                _("Role {0} does not exist").format(frappe.bold(self.role_requested))
            )

    def _validate_dates(self):
        """Validate date requirements."""
        if not self.from_datetime or not self.to_datetime:
            frappe.throw(_("From Date/Time and To Date/Time are required"))

        from_dt = get_datetime(self.from_datetime)
        to_dt = get_datetime(self.to_datetime)

        if to_dt <= from_dt:
            frappe.throw(_("To Date/Time must be greater than From Date/Time"))

        if to_dt <= now_datetime() and not frappe.flags.in_test:
            frappe.throw(_("To Date/Time must be in the future"))

    def _validate_no_overlapping_requests(self):
        """Prevent overlapping active/approved requests for same user and role."""
        from_dt = get_datetime(self.from_datetime)
        to_dt = get_datetime(self.to_datetime)

        filters = [
            ["requested_for", "=", self.requested_for],
            ["role_requested", "=", self.role_requested],
            ["status", "in", ["Pending Approval", "Approved", "Active"]],
            ["docstatus", "<", 2],
        ]

        if self.name:
            filters.append(["name", "!=", self.name])

        overlapping = frappe.db.get_all(
            "Temporary Role Access Request",
            filters=filters,
            fields=["name", "from_datetime", "to_datetime", "status"],
        )

        for req in overlapping:
            req_from = get_datetime(req.from_datetime)
            req_to = get_datetime(req.to_datetime)

            # Check if date ranges overlap
            if from_dt < req_to and to_dt > req_from:
                frappe.throw(
                    _(
                        "An overlapping {0} request ({1}) already exists for User {2} and Role {3} "
                        "from {4} to {5}."
                    ).format(
                        req.status,
                        frappe.bold(req.name),
                        frappe.bold(self.requested_for),
                        frappe.bold(self.role_requested),
                        req.from_datetime,
                        req.to_datetime,
                    )
                )

    def _validate_user_does_not_already_have_role(self):
        """Check if user already permanently has the requested role.
        Skip this check if configured to allow re-granting (via AV Tools Settings).

        Note: AV Tools Settings is a separate doctype that may not exist on all
        sites. We gracefully handle the case where the table or column is missing."""
        try:
            allow_existing = frappe.db.get_single_value(
                "AV Tools Settings", "allow_existing_role_temporary_access"
            )
            if allow_existing:
                return
        except Exception:
            # AV Tools Settings table or column may not exist on this site
            pass

        has_role = frappe.db.get_value(
            "Has Role",
            {"parent": self.requested_for, "role": self.role_requested},
        )

        if has_role:
            frappe.msgprint(
                _(
                    "Warning: User {0} already has the role {1}. "
                    "The existing permanent role will not be removed on expiry."
                ).format(
                    frappe.bold(self.requested_for),
                    frappe.bold(self.role_requested),
                ),
                alert=True,
                indicator="orange",
            )

    def _calculate_duration(self):
        """Auto-calculate duration in hours."""
        if self.from_datetime and self.to_datetime:
            from_dt = get_datetime(self.from_datetime)
            to_dt = get_datetime(self.to_datetime)
            delta = to_dt - from_dt
            self.duration_hours = flt(delta.total_seconds() / 3600, 2)

    # ---------- Role Management ----------

    def _grant_role(self):
        """Grant the requested role to the user and log the grant."""
        now = now_datetime()

        # Check if user is still enabled before granting
        user_enabled = frappe.db.get_value("User", self.requested_for, "enabled")
        if user_enabled == 0:
            frappe.log_error(
                message=f"Cannot grant role {self.role_requested} to disabled user {self.requested_for}",
                title="Temporary Role Access - User Disabled",
            )
            self.db_set("status", "Cancelled")
            return

        # Check if user already has this role (existing permanent role)
        has_role = frappe.db.get_value(
            "Has Role",
            {"parent": self.requested_for, "role": self.role_requested},
        )
        was_existing = bool(has_role)

        if not has_role:
            # Add the role to the user using Frappe's utility
            user_doc = frappe.get_doc("User", self.requested_for)
            user_doc.append("roles", {"role": self.role_requested})
            user_doc.save(ignore_permissions=True)

        # Create grant log entry
        grant_log = frappe.get_doc(
            {
                "doctype": "Temporary Role Access Grant Log",
                "user": self.requested_for,
                "role": self.role_requested,
                "request": self.name,
                "granted_on": now,
                "was_existing_role": 1 if was_existing else 0,
                "remarks": f"Role granted via Temporary Role Access Request {self.name}",
            }
        )
        grant_log.insert(ignore_permissions=True)

        # Update the request document
        self.db_set(
            {
                "role_granted": 1,
                "granted_on": now,
                "status": "Active",
            }
        )

        # Send notification
        self._send_notification(
            recipients=[self.requested_for, self.requested_by],
            subject=_("Temporary Role Access - Role {0} is now Active").format(self.role_requested),
            message=_(
                "The role {0} has been granted to {1} from {2} to {3}."
            ).format(
                frappe.bold(self.role_requested),
                frappe.bold(self.requested_for),
                self.from_datetime,
                self.to_datetime,
            ),
        )

        frappe.msgprint(
            _("Role {0} has been granted to {1}").format(
                frappe.bold(self.role_requested),
                frappe.bold(self.requested_for),
            ),
            alert=True,
        )

    def _revoke_role(self, reason="expired"):
        """Revoke the requested role from the user (only if it wasn't pre-existing).

        Args:
            reason: Either "expired" (to_datetime passed) or "cancelled" (manual cancellation).
        """
        now = now_datetime()

        # Check the grant log for this request
        grant_logs = frappe.db.get_all(
            "Temporary Role Access Grant Log",
            filters={"request": self.name, "role": self.role_requested, "user": self.requested_for},
            fields=["name", "was_existing_role"],
            order_by="creation desc",
            limit=1,
        )

        was_existing = False
        if grant_logs:
            was_existing = grant_logs[0].was_existing_role

        # Only remove if it wasn't a pre-existing role
        if not was_existing:
            user_doc = frappe.get_doc("User", self.requested_for)
            roles_to_keep = [r for r in user_doc.roles if r.role != self.role_requested]

            if len(roles_to_keep) != len(user_doc.roles):
                user_doc.roles = roles_to_keep
                user_doc.save(ignore_permissions=True)

        # Update grant log with revocation
        if grant_logs:
            revoke_remarks = (
                f"Role revoked at {now} via cancellation"
                if reason == "cancelled"
                else f"Role revoked at {now} via scheduler"
            )
            frappe.db.set_value(
                "Temporary Role Access Grant Log",
                grant_logs[0].name,
                {
                    "revoked_on": now,
                    "remarks": revoke_remarks,
                },
            )

        # Update the request document
        self.db_set(
            {
                "role_granted": 0,
                "revoked_on": now,
                "status": "Expired",
            }
        )

        # Send notification
        if reason == "cancelled":
            subject = _("Temporary Role Access - Role {0} Revoked (Cancelled)").format(self.role_requested)
            message = _(
                "The temporary access to role {0} for {1} has been revoked at {2} due to cancellation."
            ).format(
                frappe.bold(self.role_requested),
                frappe.bold(self.requested_for),
                now,
            )
        else:
            subject = _("Temporary Role Access - Role {0} has Expired").format(self.role_requested)
            message = _(
                "The temporary access to role {0} for {1} has expired at {2}."
            ).format(
                frappe.bold(self.role_requested),
                frappe.bold(self.requested_for),
                now,
            )

        self._send_notification(
            recipients=[self.requested_for, self.requested_by],
            subject=subject,
            message=message,
        )

        frappe.msgprint(
            _("Role {0} has been revoked from {1}").format(
                frappe.bold(self.role_requested),
                frappe.bold(self.requested_for),
            ),
            alert=True,
        )
    def _notify_approvers_of_new_request(self):
        """Notify approvers that a new request has been submitted."""
        approvers = frappe.db.get_all(
            "Has Role",
            filters={"role": "Role Access Approver", "parenttype": "User"},
            pluck="parent",
        )
        if not approvers:
            return

        self._send_notification(
            recipients=approvers,
            subject=_("New Temporary Role Access Request: {0}").format(self.name),
            message=_(
                "User {0} has requested temporary access to role {1} "
                "from {2} to {3}.<br><br>Reason: {4}"
            ).format(
                frappe.bold(self.requested_by),
                frappe.bold(self.role_requested),
                self.from_datetime,
                self.to_datetime,
                self.reason,
            ),
        )

    def _send_notification(self, recipients, subject, message):
        """Send a notification to recipients."""
        if isinstance(recipients, str):
            recipients = [recipients]

        # Only send if we have valid recipients
        valid_recipients = [r for r in recipients if r and frappe.db.exists("User", r)]

        if not valid_recipients:
            return

        try:
            frappe.sendmail(
                recipients=valid_recipients,
                subject=subject,
                message=message,
                reference_doctype=self.doctype,
                reference_name=self.name,
            )
        except Exception as e:
            frappe.log_error(
                message=f"Failed to send notification for {self.name}: {str(e)}",
                title="Temporary Role Access - Notification Error",
            )


# ---------- Whitelisted Methods ----------

@frappe.whitelist()
def approve_request(name, approval_remarks=None):
    """Approve a temporary role access request via Workflow action."""
    doc = frappe.get_doc("Temporary Role Access Request", name)

    if doc.status != "Pending Approval":
        frappe.throw(_("Only requests in 'Pending Approval' status can be approved"))

    if doc.requested_by == frappe.session.user:
        frappe.throw(_("You cannot approve your own request"))

    doc.approval_remarks = approval_remarks
    doc.approver = frappe.session.user
    doc.save(ignore_permissions=True)

    # Use Workflow to approve - this triggers the workflow transition
    # which sets docstatus=1 and calls on_submit
    from frappe.model.workflow import apply_workflow

    apply_workflow(doc, "Approve")

    # Send notification
    _send_status_notification(
        doc,
        _("Approved"),
        _("Your request for role {0} has been approved by {1}.").format(
            frappe.bold(doc.role_requested),
            frappe.bold(frappe.session.user),
        ),
    )

    frappe.msgprint(_("Request {0} has been approved").format(frappe.bold(name)), alert=True)


@frappe.whitelist()
def reject_request(name, approval_remarks=None):
    """Reject a temporary role access request via Workflow action."""
    doc = frappe.get_doc("Temporary Role Access Request", name)

    if doc.status != "Pending Approval":
        frappe.throw(_("Only requests in 'Pending Approval' status can be rejected"))

    doc.approval_remarks = approval_remarks
    doc.approver = frappe.session.user
    doc.save(ignore_permissions=True)

    # Use Workflow to reject
    from frappe.model.workflow import apply_workflow

    apply_workflow(doc, "Reject")

    # Send notification
    _send_status_notification(
        doc,
        _("Rejected"),
        _("Your request for role {0} has been rejected by {1}.").format(
            frappe.bold(doc.role_requested),
            frappe.bold(frappe.session.user),
        )
        + (" Reason: " + approval_remarks if approval_remarks else ""),
    )

    frappe.msgprint(_("Request {0} has been rejected").format(frappe.bold(name)), alert=True)


def _send_status_notification(doc, action_label, message):
    """Send status change notification."""
    recipients = [doc.requested_by]
    if doc.requested_by != doc.requested_for:
        recipients.append(doc.requested_for)

    valid_recipients = [r for r in recipients if r and frappe.db.exists("User", r)]
    if not valid_recipients:
        return

    try:
        frappe.sendmail(
            recipients=valid_recipients,
            subject=_("Temporary Role Access Request {0} - {1}").format(doc.name, action_label),
            message=message,
            reference_doctype=doc.doctype,
            reference_name=doc.name,
        )
    except Exception as e:
        frappe.log_error(
            message=f"Failed to send status notification for {doc.name}: {str(e)}",
            title="Temporary Role Access - Notification Error",
        )


# ---------- Scheduler Method ----------

def process_temporary_role_access():
    """Scheduled job to process role activation and expiry.
    
    Runs periodically (every 15 minutes by default) to:
    1. Activate approved requests where from_datetime <= now
    2. Expire active requests where to_datetime < now
    """
    now = now_datetime()

    # 1. Activate approved future requests
    approved_requests = frappe.db.get_all(
        "Temporary Role Access Request",
        filters={
            "status": "Approved",
            "docstatus": 1,
            "from_datetime": ("<=", now),
            "role_granted": 0,
        },
        pluck="name",
    )

    for name in approved_requests:
        try:
            doc = frappe.get_doc("Temporary Role Access Request", name)
            # Double-check user is still enabled
            user_enabled = frappe.db.get_value("User", doc.requested_for, "enabled")
            if user_enabled == 0:
                doc.db_set("status", "Cancelled")
                frappe.log_error(
                    message=f"Cannot activate - user {doc.requested_for} is disabled",
                    title="Temporary Role Access - User Disabled",
                )
                frappe.db.commit()
                continue

            doc._grant_role()
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(
                message=f"Failed to activate role for request {name}: {str(e)}",
                title="Temporary Role Access Activation Error",
            )

    # 2. Expire active requests that have passed their to_datetime
    active_requests = frappe.db.get_all(
        "Temporary Role Access Request",
        filters={
            "status": "Active",
            "docstatus": 1,
            "to_datetime": ("<", now),
            "role_granted": 1,
        },
        pluck="name",
    )

    for name in active_requests:
        try:
            doc = frappe.get_doc("Temporary Role Access Request", name)
            doc._revoke_role()
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(
                message=f"Failed to expire role for request {name}: {str(e)}",
                title="Temporary Role Access Expiry Error",
            )
