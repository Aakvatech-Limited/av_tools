"""Isolated persistence-boundary tests using synthetic documents and Frappe mocks."""

import copy
import importlib.util
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from av_tools.tax_detail_rebuild.calculation import CannotRebuild, fingerprint, reconstruct
from av_tools.tax_detail_rebuild.test_calculation import invoice


class Source(SimpleNamespace):
	def __init__(self, data):
		super().__init__(**copy.deepcopy(data))
		self.data = copy.deepcopy(data)
		self.check_permission = Mock()
		self.add_comment = Mock()
		self.notify_update = Mock()
		self.save = Mock()

	def as_dict(self):
		return copy.deepcopy(self.data)

	def get(self, key):
		return self.data.get(key)


class TestService(unittest.TestCase):
	def setUp(self):
		f = ModuleType("frappe")
		f._ = lambda text: text
		f.PermissionError = PermissionError
		f.ValidationError = ValueError
		f.session = SimpleNamespace(user="manager@example.invalid")
		f.only_for = Mock()
		f.get_doc = Mock()
		f.get_meta = Mock(return_value=SimpleNamespace(has_field=lambda field: True))
		f.get_cached_value = Mock(return_value="USD")
		f.get_precision = Mock(return_value=2)
		f.as_json = json.dumps
		f.db = Mock()
		f.qb = Mock()
		f.get_all = Mock()
		f.get_list = Mock()
		f.enqueue = Mock()
		f.clear_document_cache = Mock()
		f.log_error = Mock()
		f.get_traceback = lambda: "synthetic error"

		def throw(text, error=ValueError):
			raise error(text)

		f.throw = throw
		u = ModuleType("frappe.utils")
		u.cint = lambda value: int(value or 0)
		u.getdate = lambda value: date.fromisoformat(str(value)[:10])
		u.now_datetime = lambda: "2026-01-02 10:00:00"
		self.runtime = patch.dict(sys.modules, {"frappe": f, "frappe.utils": u})
		self.runtime.start()
		self.addCleanup(self.runtime.stop)
		spec = importlib.util.spec_from_file_location(
			"tax_rebuild_service_test", Path(__file__).with_name("service.py")
		)
		self.service = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.service)
		self.f = f
		self.doc = Source(invoice())
		self.run = SimpleNamespace(
			name="TEST-REBUILD",
			source_doctype="Purchase Invoice",
			company="Test Company",
			from_date="2026-01-01",
			to_date="2026-01-31",
			rounding_tolerance=0.5,
			max_invoices=100,
			requested_by=f.session.user,
			source_invoice=None,
			check_permission=Mock(),
		)
		self.entry = SimpleNamespace(
			name="RESULT-1",
			source_invoice=self.doc.name,
			snapshot_hash=fingerprint(self.doc.as_dict()),
			status="Ready",
			proposal_hash=fingerprint(self.service._proposal(self.run, self.doc)),
		)

	def test_rebuild_changes_only_child_rows_and_audit_metadata(self):
		self.f.get_doc.return_value = self.doc
		proposed = reconstruct(self.doc.as_dict())["rows"]
		self.f.get_all.return_value = proposed
		with patch.object(self.service, "_insert_child") as insert:
			self.assertEqual(self.service.rebuild_one(self.run, self.entry), "Rebuilt")
			self.assertEqual(insert.call_count, len(proposed))
			for call in insert.call_args_list:
				self.assertEqual(
					call.args[:4],
					("Item Wise Tax Detail", self.doc.name, self.doc.doctype, "item_wise_tax_details"),
				)
				self.assertEqual(call.args[-1], 1)
		self.doc.check_permission.assert_any_call("write")
		self.doc.save.assert_not_called()
		self.doc.add_comment.assert_called_once()
		args, kwargs = self.f.db.set_value.call_args
		self.assertEqual(set(args[2]), {"modified", "modified_by"})
		self.assertFalse(kwargs["update_modified"])

	def test_stale_preview_stops_before_any_write(self):
		self.f.get_doc.return_value = self.doc
		self.entry.snapshot_hash = "old-preview"
		with self.assertRaisesRegex(CannotRebuild, "changed after preview"):
			self.service.rebuild_one(self.run, self.entry)
		self.f.qb.from_.assert_not_called()
		self.f.db.set_value.assert_not_called()

	def test_changed_currency_precision_stops_before_any_write(self):
		self.f.get_doc.return_value = self.doc
		self.f.get_precision.return_value = 3
		with self.assertRaisesRegex(CannotRebuild, "currency settings changed"):
			self.service.rebuild_one(self.run, self.entry)
		self.f.qb.from_.assert_not_called()

	def test_permission_loss_stops_before_any_write(self):
		self.f.get_doc.return_value = self.doc
		self.doc.check_permission.side_effect = PermissionError("denied")
		with self.assertRaises(PermissionError):
			self.service.rebuild_one(self.run, self.entry)
		self.f.qb.from_.assert_not_called()

	def test_wrong_company_or_date_stops_before_any_write(self):
		self.f.get_doc.return_value = self.doc
		self.doc.company = "Other Company"
		with self.assertRaisesRegex(ValueError, "company"):
			self.service.rebuild_one(self.run, self.entry)
		self.f.qb.from_.assert_not_called()

	def test_readback_mismatch_is_rejected(self):
		self.f.get_doc.return_value = self.doc
		self.f.get_all.return_value = []
		with (
			patch.object(self.service, "_insert_child"),
			self.assertRaisesRegex(CannotRebuild, "replacement differs"),
		):
			self.service.rebuild_one(self.run, self.entry)
		self.doc.add_comment.assert_not_called()

	def test_database_zero_canonicalization_does_not_reject_exempt_adjustment(self):
		self.doc.data["items"][1]["base_net_amount"] = -0.03
		self.entry.snapshot_hash = fingerprint(self.doc.as_dict())
		proposal = self.service._proposal(self.run, self.doc)
		self.entry.proposal_hash = fingerprint(proposal)
		stored = copy.deepcopy(proposal["rows"])
		for row in stored:
			for field in ("rate", "amount", "taxable_amount"):
				if row[field] == 0:
					row[field] = 0
		self.f.get_doc.return_value = self.doc
		self.f.get_all.return_value = stored
		with patch.object(self.service, "_insert_child"):
			self.assertEqual(self.service.rebuild_one(self.run, self.entry), "Rebuilt")
		self.doc.save.assert_not_called()

	def test_repeated_repair_is_unchanged(self):
		self.doc.data["item_wise_tax_details"] = reconstruct(self.doc.as_dict())["rows"]
		self.entry.snapshot_hash = fingerprint(self.doc.as_dict())
		self.entry.proposal_hash = fingerprint(self.service._proposal(self.run, self.doc))
		self.f.get_doc.return_value = self.doc
		self.assertEqual(self.service.rebuild_one(self.run, self.entry), "Unchanged")
		self.f.qb.from_.assert_not_called()

	def test_worker_rolls_back_one_failed_invoice(self):
		self.run.status = "Queued"
		self.run.get = lambda key: [self.entry] if key == "entries" else None
		self.f.get_doc.return_value = self.run
		with (
			patch.object(self.service, "validate_criteria"),
			patch.object(self.service, "rebuild_one", side_effect=CannotRebuild("insert failure")),
		):
			self.service.process_rebuild(self.run.name)
		self.f.db.rollback.assert_called_once_with(save_point="item_tax_rebuild")
		self.assertTrue(
			any(
				call.args[0] == self.service.ENTRY and call.args[2]["status"] == "Failed"
				for call in self.f.db.set_value.call_args_list
			)
		)
		self.assertEqual(self.f.db.set_value.call_args.args[2]["status"], "Completed with Errors")

	def test_duplicate_worker_does_not_execute_running_request(self):
		self.run.status = "Running"
		self.f.get_doc.return_value = self.run
		with patch.object(self.service, "rebuild_one") as rebuild:
			self.service.process_rebuild(self.run.name)
			rebuild.assert_not_called()

	def test_queue_requires_preview_owner_and_defers_job_until_commit(self):
		self.run.status = "Previewed"
		self.run.ready_count = 1
		self.f.get_doc.return_value = self.run
		with patch.object(self.service, "validate_criteria"):
			self.service.queue_rebuild(self.run.name)
		self.assertTrue(self.f.enqueue.call_args.kwargs["enqueue_after_commit"])
		self.run.requested_by = "other@example.invalid"
		with patch.object(self.service, "validate_criteria"), self.assertRaises(PermissionError):
			self.service.queue_rebuild(self.run.name)

	def test_preview_is_read_only_for_source_and_rejects_truncated_range(self):
		self.run.status = "Draft"
		self.f.get_doc.return_value = self.run
		self.f.get_list.return_value = ["TEST-INVOICE"]
		with (
			patch.object(self.service, "validate_criteria", return_value="USD"),
			patch.object(self.service, "_source", return_value=self.doc),
			patch.object(self.service, "_insert_child") as insert,
		):
			counts = self.service.preview(self.run.name)
			self.assertEqual(counts["ready_count"], 1)
			self.assertEqual(insert.call_args.args[0], self.service.ENTRY)
			self.assertEqual(insert.call_args.args[4]["rebuild_purchase_invoice"], self.doc.name)
			self.assertIsNone(insert.call_args.args[4]["rebuild_sales_invoice"])
		self.doc.save.assert_not_called()
		self.f.qb.from_.assert_not_called()
		self.f.get_list.return_value = ["invoice"] * 101
		with (
			patch.object(self.service, "validate_criteria", return_value="USD"),
			self.assertRaisesRegex(ValueError, "Too many invoices"),
		):
			self.service.preview(self.run.name)


if __name__ == "__main__":
	unittest.main()
