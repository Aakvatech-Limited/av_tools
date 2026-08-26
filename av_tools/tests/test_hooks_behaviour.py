# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from av_tools.av_tools_hooks import parallel_approval
from av_tools.av_tools_hooks.account import add_indirect_expense_item, check_expenses_in_parent_accounts
from av_tools.av_tools_hooks.capture import get_capture_settings
from av_tools.av_tools_hooks.custom_docperm import create_custom_docperm
from av_tools.av_tools_hooks.item_remaining_qty import (
	get_item_balance,
	get_pending_delivery_item_count,
	get_pending_si_delivery_item_count,
	validate_item_remaining_qty,
	validate_items_remaining_qty,
)
from av_tools.av_tools_hooks.payroll import get_payroll_employees, validate_payroll_entry_field
from av_tools.av_tools_hooks.purchase_order import target_warehouse_based_price_list
from av_tools.av_tools_hooks.qr_utils import generate_approver_qr, get_qr_svg
from av_tools.av_tools_hooks.query_report import get_script
from av_tools.av_tools_hooks.repack_template import get_repack_template
from av_tools.av_tools_hooks.report_override import ReportOverride

SETTINGS = "AV Tools Settings"
COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"
ITEM = "_Test Item"
SCRIPT_REPORT = "Price Change History"


def set_setting(**values):
	for fieldname, value in values.items():
		frappe.db.set_single_value(SETTINGS, fieldname, value)


def make_user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
	return email


class TestCaptureAndPayrollHooks(IntegrationTestCase):
	def test_capture_settings_defaults_and_values(self):
		set_setting(
			enable_camera_capture_override=0, camera_capture_ideal_width=0, camera_capture_ideal_height=-5
		)
		self.assertEqual(
			get_capture_settings(), {"enabled": False, "ideal_width": 1920, "ideal_height": 1080}
		)
		set_setting(
			enable_camera_capture_override=1, camera_capture_ideal_width=640, camera_capture_ideal_height=480
		)
		self.assertEqual(get_capture_settings(), {"enabled": True, "ideal_width": 640, "ideal_height": 480})

	def test_payroll_helpers(self):
		self.assertEqual(get_payroll_employees("does-not-exist"), [])
		self.assertRaises(frappe.DoesNotExistError, validate_payroll_entry_field, "does-not-exist")


class TestPurchaseOrderPriceList(IntegrationTestCase):
	def make_po(self, warehouse=WAREHOUSE):
		po = frappe.new_doc("Purchase Order")
		po.company = COMPANY
		po.supplier = "_Test Supplier"
		po.append(
			"items",
			{"item_code": ITEM, "qty": 2, "rate": 5, "warehouse": warehouse, "schedule_date": nowdate()},
		)
		return po

	def test_disabled_leaves_rates_untouched(self):
		set_setting(target_warehouse_based_price_list=0)
		po = self.make_po()
		target_warehouse_based_price_list(po, "validate")
		self.assertEqual(po.items[0].rate, 5)

	def test_enabled_requires_assignment_and_applies_rate(self):
		set_setting(target_warehouse_based_price_list=1)
		self.assertRaises(
			frappe.ValidationError, target_warehouse_based_price_list, self.make_po(), "validate"
		)

		if not frappe.db.exists("Price List", "AV Test Buying"):
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": "AV Test Buying",
					"buying": 1,
					"currency": "INR",
					"enabled": 1,
				}
			).insert()
		frappe.get_doc(
			{
				"doctype": "Dynamic Price List Assignment",
				"supplier": "_Test Supplier",
				"warehouse": WAREHOUSE,
				"price_list": "AV Test Buying",
			}
		).insert()
		self.assertRaises(
			frappe.ValidationError, target_warehouse_based_price_list, self.make_po(), "validate"
		)

		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": ITEM,
				"price_list": "AV Test Buying",
				"price_list_rate": 42,
			}
		).insert()
		po = self.make_po()
		target_warehouse_based_price_list(po, "validate")
		self.assertEqual(po.items[0].rate, 42)
		self.assertEqual(po.items[0].amount, 84)

		self.assertRaises(
			frappe.ValidationError,
			target_warehouse_based_price_list,
			self.make_po(warehouse=None),
			"validate",
		)


class TestQrAndRepack(IntegrationTestCase):
	def test_qr_helpers(self):
		self.assertTrue(generate_approver_qr("hello | world").startswith("data:image/png;base64,"))
		svg = get_qr_svg("hello", size="70px")
		self.assertIn("<svg", svg)
		self.assertIn('width="70px"', svg)

	def test_repack_template_scales_quantities(self):
		template = frappe.get_doc(
			{
				"doctype": "Repack Template",
				"item_code": ITEM,
				"qty": 10,
				"default_warehouse": WAREHOUSE,
				"repack_template_details": [
					{"item_code": "_Test Item 2", "qty": 5, "default_target_warehouse": WAREHOUSE}
				],
			}
		).insert()
		rows = get_repack_template(template.name, 20)
		self.assertEqual(rows[0]["qty"], 20)
		self.assertEqual(rows[0]["s_warehouse"], WAREHOUSE)
		self.assertEqual(rows[1]["qty"], 10)
		self.assertEqual(rows[1]["t_warehouse"], WAREHOUSE)


class TestReportExtension(IntegrationTestCase):
	def extension(self, **values):
		if frappe.db.exists("Report Extension", SCRIPT_REPORT):
			doc = frappe.get_doc("Report Extension", SCRIPT_REPORT)
			doc.update(values)
			return doc.save()
		return frappe.get_doc({"doctype": "Report Extension", "report": SCRIPT_REPORT, **values}).insert()

	def test_get_script_returns_original_without_extension(self):
		frappe.db.delete("Report Extension", {"report": SCRIPT_REPORT})
		self.assertIn("script", get_script(SCRIPT_REPORT))

	def test_get_script_uses_active_extension(self):
		self.extension(active=1, script="// custom", html_format="<b>x</b>")
		result = get_script(SCRIPT_REPORT)
		self.assertEqual(result["script"], "// custom")
		self.assertEqual(result["html_format"], "<b>x</b>")
		self.extension(active=0)
		self.assertNotEqual(get_script(SCRIPT_REPORT)["script"], "// custom")

	def test_report_class_is_overridden(self):
		report = frappe.get_doc("Report", SCRIPT_REPORT)
		self.assertIsInstance(report, ReportOverride)

	def test_python_override_executes_and_falls_back(self):
		self.extension(
			active=1,
			script_python="def execute(filters=None):\n\treturn [[{'fieldname': 'a', 'label': 'A', 'fieldtype': 'Data'}], [{'a': filters.get('x')}]]",
		)
		report = frappe.get_doc("Report", SCRIPT_REPORT)
		columns, data = report.execute_script_report({"x": 7})[:2]
		self.assertEqual(data, [{"a": 7}])
		self.assertEqual(columns[0]["fieldname"], "a")

		self.extension(active=0)
		report = frappe.get_doc("Report", SCRIPT_REPORT)
		result = report.execute_script_report(
			{"company": COMPANY, "from_date": add_days(nowdate(), -30), "to_date": nowdate()}
		)
		# the original module ran (it returns None when there is no price history data)
		self.assertTrue(result is None or result[0][0]["fieldname"] != "a")

	def test_python_override_errors_are_reported(self):
		self.extension(active=1, script_python="def execute(filters=None):\n\treturn helper()")
		report = frappe.get_doc("Report", SCRIPT_REPORT)
		with self.assertRaises(frappe.ValidationError) as caught:
			report.execute_script_report({})
		self.assertIn("Missing function 'helper'", str(caught.exception))


class TestCustomDocPermHook(IntegrationTestCase):
	def test_dependent_permissions_follow_link_fields(self):
		set_setting(enable_dependent_auto_permission=1)
		role = "AV Test Perm Role"
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role}).insert()
		perm = frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": "Repack Template",
				"role": role,
				"permlevel": 0,
				"read": 1,
			}
		)
		perm.insert()
		granted = frappe.get_all("Custom DocPerm", filters={"role": role, "dependent": 1}, pluck="parent")
		self.assertIn("Item", granted)
		self.assertIn("Warehouse", granted)
		self.assertNotIn("Repack Template", granted)
		self.assertFalse(create_custom_docperm("Item", role, "Repack Template"))
		self.assertIsNone(create_custom_docperm("Address", role, "Repack Template"))
		self.assertIsNone(create_custom_docperm("DocType", role, "Repack Template"))

	def test_disabled_setting_grants_nothing(self):
		set_setting(enable_dependent_auto_permission=0)
		role = "AV Test Perm Role 2"
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role}).insert()
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": "Repack Template",
				"role": role,
				"permlevel": 0,
				"read": 1,
			}
		).insert()
		self.assertFalse(frappe.get_all("Custom DocPerm", filters={"role": role, "dependent": 1}))


class TestIndirectExpenseItem(IntegrationTestCase):
	def make_account(self, name, parent):
		return frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": name,
				"parent_account": parent,
				"company": COMPANY,
				"root_type": frappe.db.get_value("Account", parent, "root_type"),
			}
		).insert()

	def test_item_created_for_indirect_expense_and_income(self):
		set_setting(enable_indirect_expense_item_creation=1)
		expense = self.make_account("AV Test Indirect Expense", "Indirect Expenses - _TC")
		self.assertTrue(check_expenses_in_parent_accounts(expense.name))
		self.assertTrue(frappe.db.exists("Item", "AV Test Indirect Expense"))
		item = frappe.get_doc("Item", "AV Test Indirect Expense")
		self.assertEqual(item.is_purchase_item, 1)
		self.assertEqual(item.item_defaults[0].expense_account, expense.name)
		self.assertEqual(item.item_defaults[0].company, COMPANY)
		self.assertEqual(frappe.db.get_value("Account", expense.name, "item"), item.name)

		income = self.make_account("AV Test Indirect Income", "Indirect Income - _TC")
		self.assertEqual(frappe.db.get_value("Item", "AV Test Indirect Income", "is_sales_item"), 1)
		self.assertEqual(
			frappe.db.get_value("Item Default", {"parent": "AV Test Indirect Income"}, "income_account"),
			income.name,
		)

		direct = self.make_account("AV Test Direct Expense", "Direct Expenses - _TC")
		self.assertFalse(check_expenses_in_parent_accounts(direct.name))
		self.assertFalse(frappe.db.exists("Item", "AV Test Direct Expense"))

		# calling the whitelisted API again re-links the existing item instead of creating a duplicate
		self.assertEqual(add_indirect_expense_item(expense.name), item.name)

	def test_feature_disabled(self):
		set_setting(enable_indirect_expense_item_creation=0)
		self.assertRaises(frappe.ValidationError, add_indirect_expense_item, "Indirect Expenses - _TC")


class TestItemRemainingQty(IntegrationTestCase):
	def setUp(self):
		from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		self.entry = make_stock_entry(
			item_code=ITEM, target=WAREHOUSE, qty=100, basic_rate=10, company=COMPANY
		)

	def test_balance_and_pending_helpers(self):
		bin_qty = frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": WAREHOUSE}, "actual_qty")
		sle_count = frappe.db.count(
			"Stock Ledger Entry", {"item_code": ITEM, "warehouse": WAREHOUSE, "is_cancelled": 0}
		)
		self.assertGreaterEqual(
			get_item_balance(ITEM, COMPANY, WAREHOUSE),
			100,
			f"bin={bin_qty} sle={sle_count} entry={self.entry.name}/{self.entry.docstatus}",
		)
		self.assertGreaterEqual(get_item_balance(ITEM, COMPANY), 100)
		self.assertIsInstance(get_pending_delivery_item_count(ITEM, COMPANY, WAREHOUSE), (int, float))
		self.assertIsInstance(get_pending_si_delivery_item_count(ITEM, COMPANY, WAREHOUSE), (int, float))

	def test_validation_respects_flags_and_balance(self):
		set_setting(enable_validate_item_remaining_qty=0)
		self.assertIsNone(validate_item_remaining_qty(ITEM, COMPANY, WAREHOUSE, 10**9))

		set_setting(enable_validate_item_remaining_qty=1)
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 0)
		self.assertIsNone(validate_item_remaining_qty(ITEM, COMPANY, WAREHOUSE, 1))
		self.assertRaises(
			frappe.ValidationError, validate_item_remaining_qty, ITEM, COMPANY, WAREHOUSE, 10**9
		)
		self.assertRaises(
			frappe.ValidationError,
			validate_item_remaining_qty,
			"_Test Item 2",
			COMPANY,
			"_Test Warehouse 2 - _TC",
			1,
		)

		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
		self.assertIsNone(validate_item_remaining_qty(ITEM, COMPANY, WAREHOUSE, 10**9))

	def test_document_hook_skips_over_sell_rows(self):
		set_setting(enable_validate_item_remaining_qty=1)
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 0)
		invoice = frappe.new_doc("Sales Invoice")
		invoice.company = COMPANY
		invoice.customer = "_Test Customer"
		row = invoice.append(
			"items", {"item_code": ITEM, "qty": 10**6, "warehouse": WAREHOUSE, "stock_qty": 10**6}
		)
		self.assertRaises(frappe.ValidationError, validate_items_remaining_qty, invoice)
		row.allow_over_sell = 1
		self.assertIsNone(validate_items_remaining_qty(invoice))


class TestParallelApproval(IntegrationTestCase):
	approver = "av_approver@example.com"
	delegate = "av_delegate@example.com"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(cls.approver, "System Manager")
		make_user(cls.delegate, "System Manager")

	def enable(self, doctype="ToDo"):
		settings = frappe.get_single(SETTINGS)
		settings.enable_multi_approval_document = 1
		settings.approval_doctype = []
		settings.append("approval_doctype", {"doctype_name": doctype})
		settings.save()
		frappe.clear_cache(doctype=doctype)
		return settings

	def make_todo(self, *rows):
		todo = frappe.new_doc("ToDo")
		todo.description = "approval test"
		for row in rows:
			todo.append("custom_av_approver_details", row)
		with patch("frappe.sendmail"):
			todo.insert()
		return todo

	def test_feature_off_is_inert(self):
		set_setting(enable_multi_approval_document=0)
		self.assertEqual(parallel_approval._get_approval_doctypes(), set())
		self.assertEqual(parallel_approval.get_approval_doctypes_for_js(), [])
		bootinfo = frappe._dict()
		parallel_approval.boot_session(bootinfo)
		self.assertEqual(bootinfo.parallel_approval_doctypes, [])

	def test_fields_shares_and_actions(self):
		self.enable()
		self.assertTrue(
			frappe.db.exists("Custom Field", {"dt": "ToDo", "fieldname": "custom_av_approver_details"})
		)
		self.assertIn("ToDo", parallel_approval.get_approval_doctypes_for_js())

		with patch("frappe.sendmail"):
			todo = self.make_todo(
				{"approver": self.approver, "position": "Manager", "delegate_to": self.delegate}
			)
		shared = frappe.get_all(
			"DocShare", filters={"share_doctype": "ToDo", "share_name": todo.name}, pluck="user"
		)
		self.assertIn(self.approver, shared)
		self.assertIn(self.delegate, shared)

		self.assertRaises(frappe.ValidationError, parallel_approval.block_submit_if_not_approved, todo)
		self.assertRaises(
			frappe.ValidationError, parallel_approval.submit_approval_action, "ToDo", todo.name, "bogus"
		)
		self.assertRaises(
			frappe.ValidationError, parallel_approval.submit_approval_action, "ToDo", todo.name, "approve"
		)

		frappe.set_user(self.approver)
		self.addCleanup(frappe.set_user, "Administrator")
		self.assertRaises(
			frappe.ValidationError, parallel_approval.submit_approval_action, "ToDo", todo.name, "reject"
		)
		parallel_approval.submit_approval_action("ToDo", todo.name, "reject", reason="no")
		todo.reload()
		self.assertEqual(todo.custom_av_approver_details[0].rejected, 1)
		self.assertRaises(frappe.ValidationError, parallel_approval.block_submit_if_not_approved, todo)

		parallel_approval.submit_approval_action("ToDo", todo.name, "clear_rejection")
		parallel_approval.submit_approval_action("ToDo", todo.name, "approve")
		todo.reload()
		self.assertEqual(todo.custom_av_approver_details[0].approved, 1)
		self.assertIsNone(parallel_approval.block_submit_if_not_approved(todo))
		comments = frappe.get_all(
			"Comment", filters={"reference_doctype": "ToDo", "reference_name": todo.name}, pluck="content"
		)
		self.assertTrue(any("approved" in c for c in comments))

		# removing the approver removes the share
		frappe.set_user("Administrator")
		todo.custom_av_approver_details = []
		with patch("frappe.sendmail"):
			todo.save()
		self.assertFalse(
			frappe.get_all(
				"DocShare", filters={"share_doctype": "ToDo", "share_name": todo.name, "user": self.approver}
			)
		)

	def test_expired_approver_escalates_to_delegate(self):
		self.enable()
		todo = self.make_todo(
			{"approver": self.approver, "delegate_to": self.delegate, "expiry_date": add_days(nowdate(), -1)}
		)
		frappe.set_user(self.approver)
		self.addCleanup(frappe.set_user, "Administrator")
		with self.assertRaises(frappe.ValidationError) as caught:
			parallel_approval.submit_approval_action("ToDo", todo.name, "approve")
		self.assertIn("expired", str(caught.exception))
		frappe.set_user(self.delegate)
		parallel_approval.submit_approval_action("ToDo", todo.name, "approve")
		comments = frappe.get_all(
			"Comment", filters={"reference_doctype": "ToDo", "reference_name": todo.name}, pluck="content"
		)
		self.assertTrue(any("as delegate" in c for c in comments))

	def test_qr_print_format_injection_is_idempotent(self):
		frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": "AV Test ToDo PF",
				"doc_type": "ToDo",
				"custom_format": 1,
				"print_format_type": "Jinja",
				"html": "<div>todo</div>",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": "AV Test ToDo Std",
				"doc_type": "ToDo",
				"custom_format": 0,
				"print_format_type": "Jinja",
				"format_data": json.dumps([{"fieldname": "description", "fieldtype": "Text"}]),
			}
		).insert()
		parallel_approval.create_approver_qr_print_format("ToDo")
		parallel_approval.create_approver_qr_print_format("ToDo")
		html = frappe.db.get_value("Print Format", "AV Test ToDo PF", "html")
		self.assertEqual(html.count("<!-- av_tools_reviewer_qr -->"), 1)
		self.assertIn("generate_approver_qr", html)
		format_data = json.loads(frappe.db.get_value("Print Format", "AV Test ToDo Std", "format_data"))
		self.assertEqual(sum(1 for f in format_data if f.get("fieldname") == "_av_approver_qr"), 1)
		parallel_approval.delete_approver_qr_print_format("ToDo")
		self.assertNotIn(
			"av_tools_reviewer_qr", frappe.db.get_value("Print Format", "AV Test ToDo PF", "html")
		)
		format_data = json.loads(frappe.db.get_value("Print Format", "AV Test ToDo Std", "format_data"))
		self.assertFalse([f for f in format_data if f.get("fieldname") == "_av_approver_qr"])

	def test_removing_doctype_deletes_fields(self):
		self.enable()
		settings = frappe.get_single(SETTINGS)
		settings.approval_doctype = []
		settings.save()
		self.assertFalse(
			frappe.db.exists("Custom Field", {"dt": "ToDo", "fieldname": "custom_av_approver_details"})
		)
		parallel_approval.create_approval_fields("No Such DocType")
