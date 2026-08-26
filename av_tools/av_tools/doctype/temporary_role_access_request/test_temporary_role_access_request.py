# Copyright (c) 2025, Aakvatech and Contributors
# See license.txt

from typing import ClassVar

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from av_tools.av_tools.doctype.temporary_role_access_request.temporary_role_access_request import (
	approve_request,
	process_temporary_role_access,
	reject_request,
)
from av_tools.setup.temporary_role_access import (
	_create_roles,
	_create_workflow,
)

# Prevent test runner from auto-creating test records for User and Role
# since they trigger deep ERPNext dependency chains (User → Employee → Company → Cost Center)
# that fail on sites without properly configured accounting setup.
# Our setUpClass handles all necessary fixtures manually.
test_ignore = ["User", "Role"]


class TestTemporaryRoleAccessRequest(FrappeTestCase):
	"""Test suite for Temporary Role Access Request feature."""

	test_users: ClassVar[list] = []
	test_roles_created: ClassVar[list] = []
	_workflow_created = False

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures once before all tests."""
		super().setUpClass()

		# Create test users
		for email, name in [
			("test_requestor@example.com", "Test Requestor"),
			("test_approver@example.com", "Test Approver"),
			("test_target@example.com", "Test Target User"),
		]:
			if not frappe.db.exists("User", email):
				user = frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": name,
						"send_welcome_email": 0,
						"enabled": 1,
						"roles": [{"role": "System Manager"}],
					}
				)
				user.insert(ignore_permissions=True)
			cls.test_users.append(email)

		# Setup the role and workflow
		_create_roles()
		_create_workflow()

		# Assign Role Access Approver role to the test approver
		approver_user = frappe.get_doc("User", "test_approver@example.com")
		has_role = any(r.role == "Role Access Approver" for r in approver_user.roles)
		if not has_role:
			approver_user.append("roles", {"role": "Role Access Approver"})
			approver_user.save(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		"""Clean up all fixtures."""
		# Delete test requests and grant logs
		frappe.db.delete("Temporary Role Access Grant Log", {"user": ("in", cls.test_users)})
		frappe.db.delete("Temporary Role Access Request", {"requested_by": ("in", cls.test_users)})

		# Remove test roles from target user
		target_user = frappe.get_doc("User", "test_target@example.com")
		target_user.roles = [r for r in target_user.roles if r.role not in ("Test Role 1", "Test Role 2")]
		target_user.save(ignore_permissions=True)

		# Delete test roles
		for role_name in ("Test Role 1", "Test Role 2"):
			if frappe.db.exists("Role", role_name):
				frappe.db.delete("Has Role", {"role": role_name})
				frappe.delete_doc("Role", role_name)

		# Delete Workflow Action records (auto-created by workflow transitions) that reference test users
		for email in cls.test_users:
			if frappe.db.exists("User", email):
				frappe.db.delete("Workflow Action", {"user": email})
				frappe.db.delete("Workflow Action", {"completed_by": email})

		# Delete test users - wrap in try/except in case other system links remain
		for email in cls.test_users:
			if frappe.db.exists("User", email):
				frappe.db.delete("Has Role", {"parent": email})
				try:
					frappe.delete_doc("User", email)
				except frappe.LinkExistsError:
					# User may be linked to Workflow Actions or other system records
					# Disable as fallback
					frappe.db.set_value("User", email, "enabled", 0)
					frappe.msgprint(f"Could not delete {email}, disabled instead")

		# Clean up workflow
		workflow_name = "Temporary Role Access Request Workflow"
		if frappe.db.exists("Workflow", workflow_name):
			frappe.delete_doc("Workflow", workflow_name)

		# Clean up role - must delete dependent records first
		# Also delete any Workflow Action records linked to this role
		frappe.db.delete("Workflow Action", {"completed_by_role": "Role Access Approver"})
		if frappe.db.exists("Role", "Role Access Approver"):
			frappe.db.delete(
				"Temporary Role Access Grant Log",
				{"role": ("in", ["Role Access Approver", "Test Role 1", "Test Role 2"])},
			)
			frappe.db.delete(
				"Temporary Role Access Request",
				{"role_requested": ("in", ["Role Access Approver", "Test Role 1", "Test Role 2"])},
			)
			frappe.db.delete("Has Role", {"role": "Role Access Approver"})
			try:
				frappe.delete_doc("Role", "Role Access Approver")
			except (frappe.LinkValidationError, frappe.LinkExistsError):
				pass  # Role might be linked to other system data, skip deletion

		super().tearDownClass()

	def setUp(self):
		"""Reset state before each test."""
		frappe.set_user("Administrator")
		frappe.flags.in_test = True
		# Ensure test user is enabled (may have been left disabled by a failed test run)
		frappe.db.set_value("User", "test_target@example.com", "enabled", 1)

	def tearDown(self):
		"""Clean up after each test to ensure isolation."""
		# Remove any test roles granted during the test from target user
		target = frappe.get_doc("User", "test_target@example.com")
		modified = False
		for role_name in ("Test Role 1", "Test Role 2"):
			roles_to_keep = [r for r in target.roles if r.role != role_name]
			if len(roles_to_keep) != len(target.roles):
				target.roles = roles_to_keep
				modified = True
		if modified:
			target.save(ignore_permissions=True)

		# Clean up grant logs and requests created during this test
		frappe.db.delete("Temporary Role Access Grant Log", {"user": ("in", self.test_users)})
		frappe.db.delete("Temporary Role Access Request", {"requested_by": ("in", self.test_users)})

	# ========== Test Data Helpers ==========

	def _make_request(self, **kwargs):
		"""Create a draft Temporary Role Access Request."""
		defaults = {
			"doctype": "Temporary Role Access Request",
			"requested_for": "test_target@example.com",
			"requested_by": "test_requestor@example.com",
			"role_requested": "Test Role 1",
			"from_datetime": add_to_date(now_datetime(), hours=1),
			"to_datetime": add_to_date(now_datetime(), hours=5),
			"reason": "Need temporary access for a task",
		}
		defaults.update(kwargs)

		doc = frappe.get_doc(defaults)
		doc.insert(ignore_permissions=True)
		doc.reload()
		return doc

	def _submit_for_approval(self, doc):
		"""Transition from Draft to Pending Approval via workflow."""
		from frappe.model.workflow import apply_workflow

		frappe.set_user("test_requestor@example.com")
		try:
			apply_workflow(doc, "Submit for Approval")
		finally:
			frappe.set_user("Administrator")
		doc.reload()

	def _ensure_role_exists(self, role_name):
		"""Create a test role if it doesn't exist."""
		if not frappe.db.exists("Role", role_name):
			role = frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": role_name,
					"desk_access": 1,
				}
			)
			role.insert(ignore_permissions=True)

	# ========== Validation Tests ==========

	def test_disabled_user_cannot_be_requested_for(self):
		"""Request for disabled user should throw validation error."""
		frappe.db.set_value("User", "test_target@example.com", "enabled", 0)
		try:
			with self.assertRaises(frappe.ValidationError):
				self._make_request()
		finally:
			frappe.db.set_value("User", "test_target@example.com", "enabled", 1)

	def test_non_existent_role_throws_error(self):
		"""Request with non-existent role should throw validation error."""
		with self.assertRaises(frappe.ValidationError):
			self._make_request(role_requested="NonExistentRole__XYZ")

	def test_to_datetime_must_be_after_from_datetime(self):
		"""to_datetime must be greater than from_datetime."""
		base_time = add_to_date(now_datetime(), hours=1)
		with self.assertRaises(frappe.ValidationError):
			self._make_request(
				from_datetime=base_time,
				to_datetime=add_to_date(base_time, hours=-2),
			)

	def test_to_datetime_must_be_in_future(self):
		"""to_datetime must be in the future."""
		past_time = add_to_date(now_datetime(), hours=-1)
		frappe.flags.in_test = False
		try:
			with self.assertRaises(frappe.ValidationError):
				self._make_request(
					from_datetime=add_to_date(past_time, hours=-2),
					to_datetime=past_time,
				)
		finally:
			frappe.flags.in_test = True

	def test_no_overlapping_requests_same_user_role(self):
		"""Same user cannot have overlapping active/approved requests for same role."""
		doc1 = self._make_request()
		self._submit_for_approval(doc1)
		approve_request(doc1.name)

		with self.assertRaises(frappe.ValidationError):
			self._make_request(
				from_datetime=add_to_date(now_datetime(), hours=2),
				to_datetime=add_to_date(now_datetime(), hours=4),
			)

	def test_non_overlapping_requests_allowed(self):
		"""Non-overlapping requests for same user+role should be allowed."""
		self._ensure_role_exists("Test Role 1")
		doc1 = self._make_request(
			from_datetime=add_to_date(now_datetime(), hours=1),
			to_datetime=add_to_date(now_datetime(), hours=3),
		)
		self._submit_for_approval(doc1)
		approve_request(doc1.name)

		# Create a non-overlapping request (after the first one ends)
		doc2 = self._make_request(
			from_datetime=add_to_date(now_datetime(), hours=10),
			to_datetime=add_to_date(now_datetime(), hours=15),
		)
		self.assertEqual(doc2.status, "Draft")

	def test_warning_when_user_already_has_role(self):
		"""Warning should be shown when user already has the requested role."""
		self._ensure_role_exists("Test Role 1")
		target = frappe.get_doc("User", "test_target@example.com")
		target.append("roles", {"role": "Test Role 1"})
		target.save(ignore_permissions=True)

		doc = self._make_request()
		self.assertEqual(doc.status, "Draft")

	def test_duration_auto_calculated(self):
		"""Duration should be auto-calculated from dates."""
		from_dt = add_to_date(now_datetime(), hours=1)
		to_dt = add_to_date(from_dt, hours=3)
		doc = self._make_request(from_datetime=from_dt, to_datetime=to_dt)
		self.assertAlmostEqual(doc.duration_hours, 3.0, places=1)

	# ========== Workflow Transition Tests ==========

	def test_draft_to_pending_approval(self):
		"""Workflow should transition from Draft to Pending Approval."""
		doc = self._make_request()

		from frappe.model.workflow import apply_workflow

		frappe.set_user("test_requestor@example.com")
		apply_workflow(doc, "Submit for Approval")
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Pending Approval")
		self.assertEqual(doc.docstatus, 0)

	def test_approve_request_grants_role_immediately(self):
		"""Approving with from_datetime <= now should grant the role immediately."""
		self._ensure_role_exists("Test Role 1")
		doc = self._make_request(
			from_datetime=add_to_date(now_datetime(), hours=-1),
			to_datetime=add_to_date(now_datetime(), hours=3),
		)
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		approve_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Active")
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.role_granted, 1)
		self.assertIsNotNone(doc.granted_on)

		# Verify the role was assigned
		has_role = frappe.db.get_value(
			"Has Role",
			{
				"parent": "test_target@example.com",
				"role": "Test Role 1",
			},
		)
		self.assertIsNotNone(has_role)

		# Verify grant log was created
		grant_logs = frappe.db.get_all(
			"Temporary Role Access Grant Log",
			{
				"request": doc.name,
				"role": "Test Role 1",
				"user": "test_target@example.com",
			},
		)
		self.assertEqual(len(grant_logs), 1)

	def test_approve_future_request_keeps_approved(self):
		"""Approving a future-dated request should keep it as Approved (not Active)."""
		self._ensure_role_exists("Test Role 2")
		doc = self._make_request(
			role_requested="Test Role 2",
			from_datetime=add_to_date(now_datetime(), hours=2),
			to_datetime=add_to_date(now_datetime(), hours=5),
		)
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		approve_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Approved")
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.role_granted, 0)

	def test_reject_request(self):
		"""Rejecting a request should set status to Rejected."""
		doc = self._make_request()
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		reject_request(doc.name, "Not needed right now")
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Rejected")
		self.assertEqual(doc.docstatus, 0)

	def test_cancel_approved_request(self):
		"""Cancelling an approved request (no role granted yet) should work."""
		doc = self._make_request(
			from_datetime=add_to_date(now_datetime(), hours=2),
			to_datetime=add_to_date(now_datetime(), hours=5),
		)
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		approve_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Approved")

		from frappe.model.workflow import apply_workflow

		frappe.set_user("test_approver@example.com")
		apply_workflow(doc, "Cancel")
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Cancelled")
		self.assertEqual(doc.docstatus, 2)

	def test_cancel_active_request_revokes_role(self):
		"""Cancelling an active request should revoke the role."""
		self._ensure_role_exists("Test Role 1")
		doc = self._make_request(
			from_datetime=add_to_date(now_datetime(), hours=-1),
			to_datetime=add_to_date(now_datetime(), hours=5),
		)
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		approve_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Active")
		self.assertEqual(doc.role_granted, 1)
		self.assertIsNotNone(
			frappe.db.get_value(
				"Has Role",
				{
					"parent": "test_target@example.com",
					"role": "Test Role 1",
				},
			)
		)

		from frappe.model.workflow import apply_workflow

		frappe.set_user("test_approver@example.com")
		apply_workflow(doc, "Cancel")
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Cancelled")
		self.assertEqual(doc.role_granted, 0)
		self.assertIsNotNone(doc.revoked_on)
		self.assertIsNone(
			frappe.db.get_value(
				"Has Role",
				{
					"parent": "test_target@example.com",
					"role": "Test Role 1",
				},
			)
		)

	def test_resubmit_from_rejected(self):
		"""Rejected request should be resubmittable back to Draft."""
		doc = self._make_request()
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		reject_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Rejected")

		from frappe.model.workflow import apply_workflow

		frappe.set_user("test_requestor@example.com")
		apply_workflow(doc, "Resubmit")
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Draft")
		self.assertEqual(doc.docstatus, 0)

	def test_requester_cannot_approve_own_request(self):
		"""User should not be able to approve their own request."""
		doc = self._make_request()
		self._submit_for_approval(doc)

		# Switch to the requester and try to approve own request
		frappe.set_user("test_requestor@example.com")
		with self.assertRaises(frappe.ValidationError):
			approve_request(doc.name)
		frappe.set_user("Administrator")

	def test_cancel_rejected_request_blocked(self):
		"""Cancelling a rejected request should be blocked."""
		doc = self._make_request()
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		reject_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Rejected")

		# Only approved/active/pending documents should be cancellable
		from frappe.model.workflow import apply_workflow

		frappe.set_user("test_approver@example.com")
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(doc, "Cancel")
		frappe.set_user("Administrator")

	# ========== Scheduler Tests ==========

	def test_scheduler_activates_future_requests(self):
		"""Scheduler should activate approved requests whose from_datetime has passed."""
		self._ensure_role_exists("Test Role 1")
		doc = self._make_request(
			role_requested="Test Role 1",
			from_datetime=add_to_date(now_datetime(), hours=1),
			to_datetime=add_to_date(now_datetime(), hours=5),
		)
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		approve_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Approved")
		self.assertEqual(doc.role_granted, 0)

		# Simulate time passing by updating from_datetime
		frappe.db.set_value(
			"Temporary Role Access Request", doc.name, "from_datetime", add_to_date(now_datetime(), hours=-1)
		)
		frappe.db.set_value(
			"Temporary Role Access Request", doc.name, "to_datetime", add_to_date(now_datetime(), hours=5)
		)

		process_temporary_role_access()

		doc.reload()
		self.assertEqual(doc.status, "Active")
		self.assertEqual(doc.role_granted, 1)

	def test_scheduler_expires_overdue_requests(self):
		"""Scheduler should expire active requests whose to_datetime has passed."""
		self._ensure_role_exists("Test Role 1")
		doc = self._make_request(
			role_requested="Test Role 1",
			from_datetime=add_to_date(now_datetime(), hours=-3),
			to_datetime=add_to_date(now_datetime(), hours=-1),
		)
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		approve_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Active")
		self.assertEqual(doc.role_granted, 1)

		process_temporary_role_access()

		doc.reload()
		self.assertEqual(doc.status, "Expired")
		self.assertEqual(doc.role_granted, 0)

	def test_scheduler_skips_disabled_user(self):
		"""Scheduler should not activate a request for a disabled user."""
		self._ensure_role_exists("Test Role 1")
		# Use future from_datetime so approval doesn't auto-activate
		doc = self._make_request(
			role_requested="Test Role 1",
			from_datetime=add_to_date(now_datetime(), hours=2),
			to_datetime=add_to_date(now_datetime(), hours=5),
		)
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		approve_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Approved")

		# Simulate time passing - make from_datetime in the past
		frappe.db.set_value(
			"Temporary Role Access Request", doc.name, "from_datetime", add_to_date(now_datetime(), hours=-1)
		)

		# Disable the user
		frappe.db.set_value("User", "test_target@example.com", "enabled", 0)
		try:
			process_temporary_role_access()
			doc.reload()
			self.assertEqual(doc.status, "Cancelled")
			self.assertEqual(doc.role_granted, 0)
		finally:
			frappe.db.set_value("User", "test_target@example.com", "enabled", 1)

	# ========== Existing Role Protection Tests ==========

	def test_existing_role_not_removed_on_expiry(self):
		"""Permanent existing role should NOT be removed when temporary access expires."""
		self._ensure_role_exists("Test Role 1")

		# Give the user a permanent Test Role 1
		target = frappe.get_doc("User", "test_target@example.com")
		target.append("roles", {"role": "Test Role 1"})
		target.save(ignore_permissions=True)

		doc = self._make_request(
			role_requested="Test Role 1",
			from_datetime=add_to_date(now_datetime(), hours=-3),
			to_datetime=add_to_date(now_datetime(), hours=-1),
		)
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		approve_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Active")

		# Grant log should record was_existing_role = 1
		grant_logs = frappe.db.get_all(
			"Temporary Role Access Grant Log", filters={"request": doc.name}, fields=["was_existing_role"]
		)
		self.assertEqual(len(grant_logs), 1)
		self.assertEqual(grant_logs[0].was_existing_role, 1)

		process_temporary_role_access()

		doc.reload()
		self.assertEqual(doc.status, "Expired")

		# Verify the permanent role was NOT removed
		has_role = frappe.db.get_value(
			"Has Role",
			{
				"parent": "test_target@example.com",
				"role": "Test Role 1",
			},
		)
		self.assertIsNotNone(has_role, "Permanent role should not be removed on expiry")

	# ========== Grant Log Tests ==========

	def test_grant_log_created_on_grant(self):
		"""Grant log entry should be created when role is granted."""
		self._ensure_role_exists("Test Role 1")
		doc = self._make_request(
			role_requested="Test Role 1",
			from_datetime=add_to_date(now_datetime(), hours=-1),
			to_datetime=add_to_date(now_datetime(), hours=3),
		)
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		approve_request(doc.name)
		frappe.set_user("Administrator")

		grant_logs = frappe.db.get_all(
			"Temporary Role Access Grant Log",
			filters={"request": doc.name, "user": "test_target@example.com", "role": "Test Role 1"},
			fields=["name", "granted_on", "was_existing_role"],
		)
		self.assertEqual(len(grant_logs), 1)
		self.assertIsNotNone(grant_logs[0].granted_on)

	def test_grant_log_updated_on_revoke(self):
		"""Grant log should be updated with revoked_on when role is revoked."""
		self._ensure_role_exists("Test Role 1")
		doc = self._make_request(
			role_requested="Test Role 1",
			from_datetime=add_to_date(now_datetime(), hours=-3),
			to_datetime=add_to_date(now_datetime(), hours=-1),
		)
		self._submit_for_approval(doc)

		frappe.set_user("test_approver@example.com")
		approve_request(doc.name)
		frappe.set_user("Administrator")

		doc.reload()
		self.assertEqual(doc.status, "Active")

		process_temporary_role_access()

		doc.reload()
		self.assertEqual(doc.status, "Expired")

		grant_logs = frappe.db.get_all(
			"Temporary Role Access Grant Log", filters={"request": doc.name}, fields=["revoked_on"]
		)
		self.assertEqual(len(grant_logs), 1)
		self.assertIsNotNone(grant_logs[0].revoked_on, "revoked_on should be set after expiry")
