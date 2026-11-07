"""Isolated financial-boundary tests, runnable without a bench or site writes."""

import calendar
import importlib.util
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class Doc(dict):
	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value


def getdate(value=None):
	return value if isinstance(value, date) else date.fromisoformat(str(value or "2026-11-07")[:10])


def add_months(value, months):
	value = getdate(value)
	year, month = divmod(value.year * 12 + value.month - 1 + months, 12)
	return date(year, month + 1, min(value.day, calendar.monthrange(year, month + 1)[1]))


def throw(message, *args):
	raise ValueError(message)


def runtime():
	f = ModuleType("frappe")
	f._ = lambda value: value
	f._dict = Doc
	f.throw = throw
	f.PermissionError = PermissionError
	f.session = SimpleNamespace(user="accounts@example.com")
	f.as_json = json.dumps
	f.db = Mock()
	f.db.count.return_value = 1
	f.db.get_value.return_value = "TZS"
	f.get_traceback = lambda: "test failure"
	f.log_error = Mock()
	f.enqueue = Mock()
	f.get_hooks = lambda key: ["Payment Entry", "Journal Entry"]
	f.utils = ModuleType("frappe.utils")
	f.utils.cint = lambda value: int(value or 0)
	f.utils.flt = lambda value, precision=None: (
		round(float(value or 0), precision) if precision is not None else float(value or 0)
	)
	f.utils.getdate = getdate
	f.utils.now_datetime = lambda: "2026-11-07 14:00:00"
	f.utils.today = lambda: "2026-11-07"
	f.utils.get_first_day = lambda value: getdate(value).replace(day=1)
	f.utils.get_last_day = lambda value: getdate(value).replace(
		day=calendar.monthrange(getdate(value).year, getdate(value).month)[1]
	)
	f.utils.add_months = add_months
	f.utils.add_days = lambda value, days: getdate(value) + timedelta(days=days)
	return f


def load(relative, frappe):
	spec = importlib.util.spec_from_file_location("isolated_" + Path(relative).stem, ROOT / relative)
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": frappe.utils}):
		spec.loader.exec_module(module)
	return module


class TestGeneration(unittest.TestCase):
	def setUp(self):
		self.f = runtime()
		self.module = load("banking/generation.py", self.f)
		self.run = Doc(
			name="RUN-1",
			company="ACME",
			bank_account=None,
			from_date="2026-01-01",
			cutoff_date="2026-11-07",
			dry_run=0,
			status="Queued",
			requested_by=self.f.session.user,
			check_permission=Mock(),
		)
		self.bank = Doc(
			name="Bank A", account="Bank GL", company="ACME", is_company_account=1, check_permission=Mock()
		)
		self.account = Doc(
			company="ACME", account_type="Bank", account_currency="TZS", is_group=0, check_permission=Mock()
		)
		self.voucher = Doc(docstatus=1, reference_no="REF-1", check_permission=Mock())
		self.gl = Doc(
			name="GL-1",
			posting_date="2026-11-07",
			voucher_type="Journal Entry",
			voucher_no="JV-1",
			account_currency="TZS",
			debit_in_account_currency=100,
			credit_in_account_currency=0,
			remarks="Test",
			party_type=None,
			party=None,
			is_opening="No",
			account="Bank GL",
			company="ACME",
			is_cancelled=0,
			check_permission=Mock(),
		)
		self.inserted = []
		self.built = []
		self.f.get_doc = self.get_doc
		self.f.new_doc = lambda doctype: Doc(check_permission=Mock())
		self.f.get_list = lambda doctype, **kwargs: [self.bank] if doctype == "Bank Account" else self.rows
		self.module.get_existing_links = Mock(return_value=({}, {}))
		self.rows = [self.gl]

	def get_doc(self, doctype, name=None, **kwargs):
		if isinstance(doctype, dict):
			doc = Doc(doctype)
			doc.name = "BT-" + doc.custom_source_gl_entry
			doc.payment_entries = [Doc(row) for row in doc.payment_entries]
			doc.run_method = Mock()
			doc.precision = lambda field: 2
			doc.is_new = lambda: True
			doc.insert = lambda: self.inserted.append(doc)
			doc.submit = Mock(side_effect=AssertionError("Must not submit"))
			self.built.append(doc)
			return doc
		return {
			"Bank Transaction GL Generation": self.run,
			"Bank Account": self.bank,
			"Account": self.account,
			"Journal Entry": self.voucher,
			"GL Entry": self.gl,
			"Company": Doc(check_permission=Mock()),
		}[doctype]

	def skip(self, gl=None, sources=None, blocks=None):
		return self.module.get_skip_reason(
			gl or self.gl, self.run, "TZS", sources or {}, blocks or {}, ["Journal Entry"]
		)

	def test_cutoff_is_inclusive_and_checked_even_after_query(self):
		self.assertEqual(self.skip(), (None, None))
		self.gl.posting_date = "2026-11-08"
		self.assertIn("cut-off", self.skip()[0])
		self.gl.posting_date = "2025-12-31"
		self.assertIn("From Date", self.skip()[0])

	def test_exact_gl_duplicate_does_not_block_sibling_rows(self):
		self.assertEqual(self.skip(sources={"GL-1": "BT-existing"})[1], "BT-existing")
		self.gl.name = "GL-2"
		self.assertEqual(self.skip(sources={"GL-1": "BT-existing"}), (None, None))
		self.assertEqual(self.skip(blocks={("Journal Entry", "JV-1"): "BT-legacy"})[1], "BT-legacy")

	def test_ambiguous_negative_zero_and_currency_mismatch_are_not_generated(self):
		for debit, credit in ((0, 0), (-100, 0), (100, 100)):
			self.gl.debit_in_account_currency, self.gl.credit_in_account_currency = debit, credit
			self.assertIsNotNone(self.skip()[0])
		self.gl.debit_in_account_currency, self.gl.credit_in_account_currency = 100, 0
		self.gl.account_currency = "USD"
		self.assertIn("currency", self.skip()[0])

	def test_each_split_gl_row_creates_its_own_draft_with_zero_allocation(self):
		second = Doc(self.gl)
		second.name, second.debit_in_account_currency = "GL-2", 40
		self.rows.append(second)
		counts = dict.fromkeys(["scanned_count", "eligible_count", "created_count", "skipped_count"], 0)
		self.module.process_bank(self.run, self.bank.name, counts, [])
		self.assertEqual(counts["created_count"], 2)
		self.assertEqual([bt.deposit for bt in self.inserted], [100, 40])
		for bt in self.inserted:
			self.assertEqual(bt.docstatus, 0)
			self.assertEqual(bt.payment_entries[0].payment_entry, "JV-1")
			self.assertEqual(bt.payment_entries[0].allocated_amount, 0)
			bt.submit.assert_not_called()

	def test_preview_runs_validation_and_never_inserts(self):
		self.run.dry_run = 1
		counts = dict.fromkeys(["scanned_count", "eligible_count", "created_count", "skipped_count"], 0)
		self.module.process_bank(self.run, self.bank.name, counts, [])
		self.assertEqual(counts["eligible_count"], 1)
		self.assertFalse(self.inserted)
		self.built[0].run_method.assert_any_call("before_validate")

	def test_cancelled_voucher_and_ambiguous_mapping_are_skipped(self):
		self.voucher.docstatus = 2
		counts = dict.fromkeys(["scanned_count", "eligible_count", "created_count", "skipped_count"], 0)
		self.module.process_bank(self.run, self.bank.name, counts, [])
		self.assertEqual(counts["skipped_count"], 1)
		self.f.db.count.return_value = 2
		self.module.process_bank(self.run, self.bank.name, counts, [])
		self.assertFalse(self.inserted)

	def test_bank_read_permission_is_not_bypassed(self):
		self.bank.check_permission.side_effect = PermissionError
		with self.assertRaises(PermissionError):
			self.module.process_bank(self.run, self.bank.name, {}, [])
		self.assertFalse(self.inserted)

	def test_job_uses_requester_and_queue_is_after_commit(self):
		self.module.enqueue_generation(self.run)
		kwargs = self.f.enqueue.call_args.kwargs
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.assertTrue(kwargs["deduplicate"])
		self.run.requested_by = "someone-else@example.com"
		with self.assertRaises(ValueError):
			self.module.process_generation(self.run.name)
		self.f.db.commit.assert_not_called()

	def test_job_rolls_back_all_created_rows_on_failure(self):
		with patch.object(self.module, "process_bank", side_effect=RuntimeError("insertion failed")):
			with self.assertRaises(RuntimeError):
				self.module.process_generation(self.run.name)
		self.f.db.rollback.assert_called_once()
		result = self.f.db.set_value.call_args.args[2]
		self.assertEqual(result["status"], "Failed")
		self.assertEqual(result["created_count"], 0)
		self.assertTrue(json.loads(result["result_log"])["rolled_back"])

	def test_live_insert_guard_rejects_preview_and_submission(self):
		doc = self.module.build_transaction(self.run, self.bank, self.gl, self.voucher, "TZS")
		for dry_run, status, docstatus in ((1, "Running", 0), (0, "Completed", 0), (0, "Running", 1)):
			self.run.dry_run, self.run.status, doc.docstatus = dry_run, status, docstatus
			with self.assertRaises(ValueError):
				self.module.require_live_generation(doc)
		self.run.dry_run, self.run.status, doc.docstatus = 0, "Running", 0
		self.module.require_live_generation(doc)

	def test_source_guard_revalidates_cutoff_amount_voucher_and_reservation(self):
		doc = self.module.build_transaction(self.run, self.bank, self.gl, self.voucher, "TZS")
		self.module.validate_source(doc)
		self.assertEqual(doc.custom_active_gl_key, "GL-1")
		for key, value in (("deposit", 999), ("date", "2026-11-08"), ("currency", "USD")):
			old = doc[key]
			doc[key] = value
			with self.assertRaises(ValueError):
				self.module.validate_source(doc)
			doc[key] = old
		self.run.cutoff_date = "2026-11-06"
		with self.assertRaises(ValueError):
			self.module.validate_source(doc)
		self.run.cutoff_date = "2026-11-07"
		self.module.get_existing_links.return_value = ({}, {("Journal Entry", "JV-1"): "BT-imported"})
		with self.assertRaises(ValueError):
			self.module.validate_source(doc)

	def test_source_release_keeps_the_audit_link(self):
		doc = Doc(custom_source_gl_entry="GL-1", custom_active_gl_key="GL-1")
		self.module.release_source(doc)
		self.assertEqual(doc.custom_source_gl_entry, "GL-1")
		self.assertIsNone(doc.custom_active_gl_key)


class TestStatement(unittest.TestCase):
	def setUp(self):
		self.f = runtime()
		self.bank = Doc(company="ACME", account="Bank GL", is_company_account=1, check_permission=Mock())
		self.f.get_doc = lambda *args: self.bank
		self.rows = [
			Doc(name="OPEN", date="2025-12-31", deposit=100, withdrawal=0, currency="TZS"),
			Doc(name="A", date="2026-01-20", deposit=25, withdrawal=0, currency="TZS"),
			Doc(name="B", date="2026-03-02", deposit=0, withdrawal=40, currency="TZS"),
		]
		self.f.get_list = Mock(side_effect=lambda *args, **kwargs: self.rows)
		self.module = load("av_tools/report/bank_transaction_statement/bank_transaction_statement.py", self.f)
		self.filters = dict(
			company="ACME",
			bank_account="Bank A",
			time_span="Period",
			from_date="2026-01-15",
			to_date="2026-03-10",
		)

	def test_running_balance_and_monthly_closing_agree_with_empty_month(self):
		_, detail, _ = self.module.execute(self.filters)
		_, monthly, _ = self.module.execute({**self.filters, "view": "Monthly Summary"})
		self.assertEqual([r["balance"] for r in detail], [100, 125, 85, 85])
		self.assertEqual([r["balance"] for r in monthly], [125, 125, 85, 85])
		self.assertEqual(monthly[0]["period_from"], date(2026, 1, 15))
		self.assertEqual(monthly[2]["period_to"], date(2026, 3, 10))
		self.assertEqual(monthly[-1]["deposit"], detail[-1]["deposit"])
		self.assertEqual(monthly[-1]["withdrawal"], detail[-1]["withdrawal"])
		self.assertEqual(self.f.get_list.call_args.kwargs["filters"]["docstatus"], 1)

	def test_months_are_separate_across_years_and_no_transactions_carries_opening(self):
		self.rows = self.rows[:1]
		_, rows, _ = self.module.execute(
			{**self.filters, "view": "Monthly Summary", "from_date": "2026-12-01", "to_date": "2027-01-31"}
		)
		self.assertEqual([r["month"] for r in rows], ["2026-12", "2027-01", "Period Total"])
		self.assertEqual([r["balance"] for r in rows], [100, 100, 100])

	def test_relative_span_is_resolved_on_each_execution(self):
		self.module.execute({**self.filters, "time_span": "This Month"})
		self.assertEqual(self.f.get_list.call_args.kwargs["filters"]["date"], ["<=", date(2026, 11, 30)])
		self.f.utils.today = lambda: "2026-12-01"
		self.module.execute({**self.filters, "time_span": "This Month"})
		self.assertEqual(self.f.get_list.call_args.kwargs["filters"]["date"], ["<=", date(2026, 12, 31)])

	def test_currency_date_and_bank_company_validation(self):
		self.rows[1].currency = "USD"
		with self.assertRaises(ValueError):
			self.module.execute(self.filters)
		with self.assertRaises(ValueError):
			self.module.execute({**self.filters, "from_date": "2027-01-01"})
		self.bank.company = "OTHER"
		with self.assertRaises(ValueError):
			self.module.execute(self.filters)


class TestPackaging(unittest.TestCase):
	def setup_module(self):
		f = runtime()
		f.clear_cache = Mock()
		f.client_cache = Mock()
		f.reload_doc = Mock()
		f.get_app_path = lambda app, *parts: str(ROOT.joinpath(*parts))
		f.get_all = Mock(return_value=[])
		f.db.exists.return_value = True
		custom_fields = ModuleType("frappe.custom.doctype.custom_field.custom_field")
		custom_fields.create_custom_fields = Mock()
		with patch.dict(sys.modules, {custom_fields.__name__: custom_fields}):
			module = load("banking/setup.py", f)
		return f, module, custom_fields.create_custom_fields

	def test_migration_adopts_in_place_and_disables_only_prototype_scripts(self):
		f, module, create_fields = self.setup_module()
		module.prepare_site()
		f.db.set_value.assert_any_call(
			"DocType",
			"Bank Transaction GL Generation",
			{"custom": 0, "module": "Av Tools"},
			update_modified=False,
		)
		for _ in range(2):
			module.after_migrate()
		self.assertEqual(create_fields.call_count, 2)
		f.db.delete.assert_not_called()
		f.db.set_value.assert_any_call(
			"Server Script", "Bank Transaction GL Generation - Worker", "disabled", 1, update_modified=False
		)
		f.db.set_value.assert_any_call(
			"Client Script",
			"Bank Transaction - Generate from GL Entries",
			"enabled",
			0,
			update_modified=False,
		)
		f.client_cache.delete_value.assert_called_with("server_script_map")
		for call in f.db.set_value.call_args_list:
			if call.args[0] in ("Client Script", "Server Script"):
				self.assertIn(call.args[1], module.CLIENT_SCRIPTS + module.SERVER_SCRIPTS)

	def test_migration_refuses_to_orphan_active_legacy_job(self):
		f, module, _ = self.setup_module()
		f.get_all.side_effect = [[Doc(name="RUN-pending")], [Doc(status="started")]]
		with self.assertRaises(ValueError):
			module.prepare_site()
		f.db.set_value.assert_not_called()

	def test_shipped_permissions_only_use_standard_roles(self):
		paths = [
			"av_tools/doctype/bank_transaction_gl_generation/bank_transaction_gl_generation.json",
			"av_tools/report/bank_transaction_statement/bank_transaction_statement.json",
		]
		for path in paths:
			doc = json.loads((ROOT / path).read_text())
			for permission in doc.get("permissions", doc.get("roles", [])):
				self.assertIn(permission["role"], {"System Manager", "Accounts Manager", "Accounts User"})
		self.assertFalse(list((ROOT / "banking").glob("**/role/*.json")))

	def test_active_source_key_is_unique_and_not_copied(self):
		fields = json.loads(
			(
				ROOT / "patches/custom_fields/custom_fields_json/bank_transaction_gl_generation.json"
			).read_text()
		)
		key = next(row for row in fields if row["fieldname"] == "custom_active_gl_key")
		self.assertEqual(key["unique"], 1)
		self.assertEqual(key["no_copy"], 1)


if __name__ == "__main__":
	unittest.main()
