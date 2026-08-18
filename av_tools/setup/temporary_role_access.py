# Copyright (c) 2025, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def setup_temporary_role_access():
    """Setup workflow, roles, and required data for Temporary Role Access feature."""
    _create_roles()
    _create_workflow_states()
    _create_workflow_action_masters()
    _create_workflow()


def _create_roles():
    """Create the Role Access Approver role if it doesn't exist."""
    if not frappe.db.exists("Role", "Role Access Approver"):
        role = frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": "Role Access Approver",
                "desk_access": 1,
            }
        )
        role.insert(ignore_permissions=True)
        frappe.msgprint(_("Role 'Role Access Approver' created"))


def _create_workflow_states():
    """Create Workflow State records required by the workflow."""
    states = [
        "Draft",
        "Pending Approval",
        "Approved",
        "Active",
        "Expired",
        "Rejected",
        "Cancelled",
    ]
    for state_name in states:
        if not frappe.db.exists("Workflow State", state_name):
            state = frappe.get_doc(
                {
                    "doctype": "Workflow State",
                    "workflow_state_name": state_name,
                }
            )
            state.insert(ignore_permissions=True)


def _create_workflow_action_masters():
    """Create Workflow Action Master records required by the workflow."""
    actions = [
        "Submit for Approval",
        "Approve",
        "Reject",
        "Cancel",
        "Resubmit",
    ]
    for action_name in actions:
        if not frappe.db.exists("Workflow Action Master", action_name):
            action = frappe.get_doc(
                {
                    "doctype": "Workflow Action Master",
                    "workflow_action_name": action_name,
                }
            )
            action.insert(ignore_permissions=True)


def _create_workflow():
    """Create the workflow for Temporary Role Access Request.

    Note: The 'allowed' field in Workflow Transition is a Link to Role,
    so only ONE role per transition row is allowed. For transitions that
    need multiple roles, create separate rows.
    """
    workflow_name = "Temporary Role Access Request Workflow"

    if frappe.db.exists("Workflow", workflow_name):
        return

    workflow = frappe.get_doc(
        {
            "doctype": "Workflow",
            "workflow_name": workflow_name,
            "document_type": "Temporary Role Access Request",
            "is_active": 1,
            "override_status": 0,
            "send_email_alert": 0,
            "states": [
                {
                    "state": "Draft",
                    "doc_status": 0,
                    "update_field": "status",
                    "update_value": "Draft",
                    "allow_edit": "All",
                },
                {
                    "state": "Pending Approval",
                    "doc_status": 0,
                    "update_field": "status",
                    "update_value": "Pending Approval",
                    "allow_edit": "All",
                },
                {
                    "state": "Approved",
                    "doc_status": 1,
                    "update_field": "status",
                    "update_value": "Approved",
                    "allow_edit": "Role Access Approver",
                },
                {
                    "state": "Active",
                    "doc_status": 1,
                    "update_field": "status",
                    "update_value": "Active",
                    "allow_edit": "System Manager",
                },
                {
                    "state": "Expired",
                    "doc_status": 1,
                    "update_field": "status",
                    "update_value": "Expired",
                    "allow_edit": "System Manager",
                },
                {
                    "state": "Rejected",
                    "doc_status": 0,
                    "update_field": "status",
                    "update_value": "Rejected",
                    "allow_edit": "Role Access Approver",
                },
                {
                    "state": "Cancelled",
                    "doc_status": 2,
                    "update_field": "status",
                    "update_value": "Cancelled",
                    "allow_edit": "System Manager",
                },
            ],
            "transitions": [
                {
                    "state": "Draft",
                    "action": "Submit for Approval",
                    "next_state": "Pending Approval",
                    "allowed": "All",
                    "allow_self_approval": 1,
                    "condition": "doc.requested_by == frappe.session.user",
                },
                {
                    "state": "Pending Approval",
                    "action": "Approve",
                    "next_state": "Approved",
                    "allowed": "Role Access Approver",
                    "allow_self_approval": 0,
                },
                {
                    "state": "Pending Approval",
                    "action": "Reject",
                    "next_state": "Rejected",
                    "allowed": "Role Access Approver",
                    "allow_self_approval": 0,
                },
                # Split multi-role Cancel into separate rows (one per role)
                {
                    "state": "Approved",
                    "action": "Cancel",
                    "next_state": "Cancelled",
                    "allowed": "System Manager",
                    "allow_self_approval": 0,
                },
                {
                    "state": "Approved",
                    "action": "Cancel",
                    "next_state": "Cancelled",
                    "allowed": "Role Access Approver",
                    "allow_self_approval": 0,
                },
                {
                    "state": "Active",
                    "action": "Cancel",
                    "next_state": "Cancelled",
                    "allowed": "System Manager",
                    "allow_self_approval": 0,
                },
                {
                    "state": "Active",
                    "action": "Cancel",
                    "next_state": "Cancelled",
                    "allowed": "Role Access Approver",
                    "allow_self_approval": 0,
                },
                {
                    "state": "Rejected",
                    "action": "Resubmit",
                    "next_state": "Draft",
                    "allowed": "All",
                    "allow_self_approval": 1,
                    "condition": "doc.requested_by == frappe.session.user",
                },
            ],
        }
    )
    workflow.insert(ignore_permissions=True)
    frappe.msgprint(_("Workflow 'Temporary Role Access Request Workflow' created"))
