"""Permission-checked preview, audited repair and background batch processing."""

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime

from av_tools.tax_detail_rebuild.calculation import (
	SOURCES,
	CannotRebuild,
	fingerprint,
	number,
	reconstruct,
	semantic_rows,
)

RUN = "Item Wise Tax Detail Rebuild"
ENTRY = "Item Wise Tax Detail Rebuild Entry"
DETAIL = "Item Wise Tax Detail"
MAX_INVOICES = 200


def authorize():
	frappe.only_for(("Accounts Manager", "System Manager"))


def validate_criteria(run):
	authorize()
	if run.source_doctype not in SOURCES:
		frappe.throw(_("Select Sales Invoice or Purchase Invoice."))
	if not frappe.get_meta(run.source_doctype).has_field("item_wise_tax_details"):
		frappe.throw(_("This feature requires ERPNext v16 item-wise tax details."))
	frappe.get_doc("Company", run.company).check_permission("read")
	if not run.from_date or not run.to_date or getdate(run.from_date) > getdate(run.to_date):
		frappe.throw(_("Enter a valid inclusive posting date range."))
	if not 1 <= cint(run.max_invoices) <= MAX_INVOICES:
		frappe.throw(_("Maximum Invoices must be between 1 and 200."))
	if not 0 <= number(run.rounding_tolerance, "Tolerance") <= number("0.5", "Maximum"):
		frappe.throw(_("Rounding tolerance must be between 0 and 0.5 in company currency."))
	return frappe.get_doc("Company", run.company).default_currency


def _source(run, name, lock=False):
	doc = frappe.get_doc(run.source_doctype, name, for_update=lock)
	doc.check_permission("read")
	doc.check_permission("write")
	if doc.company != run.company or doc.docstatus != 1:
		frappe.throw(_("Source company or submitted status has changed."))
	if not getdate(run.from_date) <= getdate(doc.posting_date) <= getdate(run.to_date):
		frappe.throw(_("Source posting date is outside the preview range."))
	return doc


def _proposal(run, doc):
	currency = frappe.get_cached_value("Company", run.company, "default_currency")
	precision = frappe.get_precision(DETAIL, "amount", currency=currency)
	result = reconstruct(doc.as_dict(), precision=precision, tolerance=run.rounding_tolerance)
	result["configuration"] = {
		"currency": currency,
		"precision": precision,
		"tolerance": str(run.rounding_tolerance),
	}
	return result


def _insert_child(doctype, parent, parenttype, parentfield, values, idx, docstatus=0):
	row = frappe.get_doc(
		{
			"doctype": doctype,
			**values,
			"parent": parent,
			"parenttype": parenttype,
			"parentfield": parentfield,
			"idx": idx,
			"docstatus": docstatus,
		}
	)
	row.set_new_name()
	row.db_insert()


def preview(run_name):
	authorize()
	run = frappe.get_doc(RUN, run_name, for_update=True)
	run.check_permission("write")
	if run.status != "Draft":
		frappe.throw(_("Create a new request to preview again; existing previews are retained for audit."))
	currency = validate_criteria(run)
	criteria = {
		"company": run.company,
		"docstatus": 1,
		"posting_date": ["between", [run.from_date, run.to_date]],
	}
	if run.source_invoice:
		criteria["name"] = run.source_invoice
	names = frappe.get_list(
		run.source_doctype,
		filters=criteria,
		pluck="name",
		order_by="posting_date asc, name asc",
		limit_page_length=cint(run.max_invoices) + 1,
	)
	if len(names) > cint(run.max_invoices):
		frappe.throw(
			_("Too many invoices. Narrow the dates or select a single invoice; no preview was saved.")
		)
	if not names:
		frappe.throw(_("No accessible submitted invoices match the criteria."))
	counts = {"ready_count": 0, "blocked_count": 0, "unchanged_count": 0}
	for idx, name in enumerate(names, 1):
		values = {
			"source_doctype": run.source_doctype,
			"source_invoice": name,
			"status": "Blocked",
			"reason": "",
			"snapshot_hash": "",
		}
		try:
			source = _source(run, name)
			values["snapshot_hash"] = fingerprint(source.as_dict())
			values["before_details"] = frappe.as_json(source.get("item_wise_tax_details") or [])
			result = _proposal(run, source)
			values.update(
				status="Ready" if result["changed"] else "Unchanged",
				proposal_hash=fingerprint(result),
				proposed_details=frappe.as_json(result["rows"]),
				controls=frappe.as_json(result["controls"]),
				old_row_count=len(source.get("item_wise_tax_details") or []),
				new_row_count=len(result["rows"]),
			)
			values["reason"] = (
				"Posted tax totals reconcile; derived details can be replaced."
				if result["changed"]
				else "Stored details already match the reconstruction."
			)
		except (CannotRebuild, frappe.PermissionError, frappe.ValidationError) as exc:
			values["reason"] = str(exc)
		count_field = {"Ready": "ready_count", "Unchanged": "unchanged_count", "Blocked": "blocked_count"}[
			values["status"]
		]
		counts[count_field] += 1
		_insert_child(ENTRY, run.name, RUN, "entries", values, idx)
	frappe.db.set_value(
		RUN,
		run.name,
		{
			**counts,
			"status": "Previewed",
			"currency": currency,
			"requested_by": frappe.session.user,
			"previewed_at": now_datetime(),
			"scanned_count": len(names),
			"rebuilt_count": 0,
			"failed_count": 0,
			"failure_reason": None,
			"started_at": None,
			"finished_at": None,
		},
	)
	return counts


def queue_rebuild(run_name):
	authorize()
	run = frappe.get_doc(RUN, run_name, for_update=True)
	run.check_permission("write")
	if run.status != "Previewed" or not run.ready_count:
		frappe.throw(_("Preview first; at least one invoice must be Ready."))
	if run.requested_by != frappe.session.user:
		frappe.throw(_("Only the user who previewed this request can rebuild it."), frappe.PermissionError)
	validate_criteria(run)
	frappe.db.set_value(RUN, run.name, "status", "Queued")
	frappe.enqueue(
		"av_tools.tax_detail_rebuild.service.process_rebuild",
		queue="long",
		timeout=3600,
		enqueue_after_commit=True,
		job_id=f"item-wise-tax-rebuild:{run.name}",
		deduplicate=True,
		run_name=run.name,
	)
	return {"status": "Queued"}


def rebuild_one(run, entry):
	"""Called inside a per-invoice savepoint. Never save/recalculate the invoice."""
	source = _source(run, entry.source_invoice, lock=True)
	if fingerprint(source.as_dict()) != entry.snapshot_hash:
		raise CannotRebuild("Invoice or item-wise details changed after preview. Create a new preview.")
	result = _proposal(run, source)
	if fingerprint(result) != entry.proposal_hash:
		raise CannotRebuild(
			"Reconstruction rules or currency settings changed after preview. Create a new preview."
		)
	# Recompute, never trust JSON posted by a client or recorded in the preview.
	if not result["changed"]:
		return "Unchanged"
	Detail = frappe.qb.DocType(DETAIL)
	(
		frappe.qb.from_(Detail)
		.delete()
		.where(Detail.parent == source.name)
		.where(Detail.parenttype == source.doctype)
		.where(Detail.parentfield == "item_wise_tax_details")
	).run()
	for idx, values in enumerate(result["rows"], 1):
		_insert_child(
			DETAIL, source.name, source.doctype, "item_wise_tax_details", values, idx, source.docstatus
		)
	stored = frappe.get_all(
		DETAIL,
		filters={"parent": source.name, "parenttype": source.doctype, "parentfield": "item_wise_tax_details"},
		fields=["item_row", "tax_row", "rate", "amount", "taxable_amount"],
		limit_page_length=0,
	)
	if semantic_rows(stored) != semantic_rows(result["rows"]):
		raise CannotRebuild("Stored replacement differs from the verified proposal; changes rolled back.")
	stamp = now_datetime()
	frappe.db.set_value(
		source.doctype,
		source.name,
		{"modified": stamp, "modified_by": frappe.session.user},
		update_modified=False,
	)
	source.modified = stamp
	source.modified_by = frappe.session.user
	source.add_comment(
		"Info",
		f"Item-wise tax details rebuilt from saved transaction rates by {frappe.session.user}. Audit request: {run.name}. Invoice financial fields and GL entries were not recalculated.",
	)
	frappe.clear_document_cache(source.doctype, source.name)
	source.notify_update()
	return "Rebuilt"


def process_rebuild(run_name):
	"""Background jobs inherit the requester; verify that identity and permissions again."""
	run = frappe.get_doc(RUN, run_name, for_update=True)
	if run.status != "Queued":
		return
	try:
		authorize()
		run.check_permission("write")
		if run.requested_by != frappe.session.user:
			frappe.throw(_("Requesting user does not match the job user."), frappe.PermissionError)
		validate_criteria(run)
		frappe.db.set_value(RUN, run.name, {"status": "Running", "started_at": now_datetime()})
		frappe.db.commit()
		rebuilt, failed = 0, 0
		for entry in run.get("entries") or []:
			if entry.status != "Ready":
				continue
			frappe.db.savepoint("item_tax_rebuild")
			try:
				status = rebuild_one(run, entry)
				frappe.db.set_value(
					ENTRY, entry.name, {"status": status, "reason": "Verified replacement saved."}
				)
				rebuilt += status == "Rebuilt"
			except Exception as exc:
				frappe.db.rollback(save_point="item_tax_rebuild")
				frappe.db.set_value(ENTRY, entry.name, {"status": "Failed", "reason": str(exc)[:2000]})
				failed += 1
			frappe.db.set_value(RUN, run.name, {"rebuilt_count": rebuilt, "failed_count": failed})
			frappe.db.commit()
		frappe.db.set_value(
			RUN,
			run.name,
			{"status": "Completed with Errors" if failed else "Completed", "finished_at": now_datetime()},
		)
		frappe.db.commit()
	except Exception as exc:
		frappe.db.rollback()
		frappe.db.set_value(
			RUN,
			run.name,
			{"status": "Failed", "finished_at": now_datetime(), "failure_reason": str(exc)[:2000]},
		)
		frappe.log_error(title="Item-wise tax detail rebuild failed", message=frappe.get_traceback())
		frappe.db.commit()
		raise
