"""Generate draft bank movements from individual, unallocated GL rows."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime

RUN_DOCTYPE = "Bank Transaction GL Generation"
WORKER = "av_tools.banking.generation.process_generation"


def validate_request(doc):
	frappe.get_doc("Company", doc.company).check_permission("read")
	frappe.new_doc("Bank Transaction").check_permission("create")
	if not doc.cutoff_date:
		frappe.throw(_("Cut-off Date is required."))
	if doc.from_date and getdate(doc.from_date) > getdate(doc.cutoff_date):
		frappe.throw(_("From Date cannot be after Cut-off Date."))
	if doc.bank_account:
		bank = frappe.get_doc("Bank Account", doc.bank_account)
		bank.check_permission("read")
		if not bank.is_company_account or bank.company != doc.company or not bank.account:
			frappe.throw(_("Select a company bank account with a GL account in the selected Company."))


def enqueue_generation(doc):
	frappe.enqueue(
		WORKER,
		queue="long",
		timeout=3600,
		enqueue_after_commit=True,
		job_id=f"av-tools-bank-gl:{doc.name}",
		deduplicate=True,
		generation_run=doc.name,
	)


def process_generation(generation_run):
	"""Run as the requester; commit all drafts together or roll them all back.

	Account locks serialize overlapping runs. The unique active GL key also
	protects individual sources if a different writer inserts concurrently.
	"""
	run = frappe.get_doc(RUN_DOCTYPE, generation_run, for_update=True)
	run.check_permission("read")
	if run.requested_by != frappe.session.user:
		frappe.throw(_("Only the requesting user can execute this generation run."), frappe.PermissionError)
	if run.status != "Queued":
		return
	frappe.db.set_value(RUN_DOCTYPE, run.name, {"status": "Running", "started_at": now_datetime()})
	frappe.db.commit()
	counts = dict(scanned_count=0, eligible_count=0, created_count=0, skipped_count=0, failed_count=0)
	log = []
	try:
		validate_request(run)
		banks = frappe.get_list(
			"Bank Account",
			filters={"company": run.company, "is_company_account": 1},
			fields=["name", "account"],
			order_by="name asc",
			limit_page_length=0,
		)
		selected = [b for b in banks if not run.bank_account or b.name == run.bank_account]
		if not selected:
			frappe.throw(_("No accessible company bank account was found."))
		for bank_row in selected:
			process_bank(run, bank_row.name, counts, log)
		frappe.db.set_value(
			RUN_DOCTYPE,
			run.name,
			{
				**counts,
				"status": "Completed",
				"finished_at": now_datetime(),
				"result_log": frappe.as_json(log),
			},
		)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.db.set_value(
			RUN_DOCTYPE,
			run.name,
			{
				**counts,
				"status": "Failed",
				"created_count": 0,
				"failed_count": 1,
				"finished_at": now_datetime(),
				"result_log": frappe.as_json(
					{
						"error": frappe.get_traceback(),
						"rolled_back": True,
						"message": "All draft creations in this run were rolled back.",
					}
				),
			},
		)
		frappe.db.commit()
		frappe.log_error(
			title="GL Bank Transaction Generation Failed",
			reference_doctype=RUN_DOCTYPE,
			reference_name=run.name,
		)
		raise


def process_bank(run, bank_name, counts, log):
	bank = frappe.get_doc("Bank Account", bank_name, for_update=True)
	bank.check_permission("read")
	reason = None
	if not bank.account:
		reason = "No linked GL account"
	elif frappe.db.count("Bank Account", {"is_company_account": 1, "account": bank.account}) != 1:
		reason = "Multiple Bank Accounts map to this GL account; resolve the mapping first"
	if reason:
		log.append({"bank_account": bank.name, "result": "Skipped bank", "reason": reason})
		return
	account = frappe.get_doc("Account", bank.account)
	account.check_permission("read")
	if account.company != run.company or account.account_type != "Bank" or account.is_group:
		frappe.throw(_("Invalid bank GL account mapping for {0}.").format(bank.name))
	currency = account.account_currency or frappe.get_cached_value("Company", run.company, "default_currency")
	filters = {
		"company": run.company,
		"account": bank.account,
		"is_cancelled": 0,
		"posting_date": ["<=", getdate(run.cutoff_date)],
	}
	if run.from_date:
		filters["posting_date"] = ["between", [getdate(run.from_date), getdate(run.cutoff_date)]]
	rows = frappe.get_list(
		"GL Entry",
		filters=filters,
		fields=[
			"name",
			"posting_date",
			"voucher_type",
			"voucher_no",
			"account_currency",
			"debit_in_account_currency",
			"credit_in_account_currency",
			"remarks",
			"party_type",
			"party",
			"is_opening",
		],
		order_by="posting_date asc, creation asc, name asc",
		limit_page_length=0,
	)
	sources, voucher_blocks = get_existing_links(bank.account)
	allowed_types = frappe.get_hooks("bank_reconciliation_doctypes")
	for gl in rows:
		counts["scanned_count"] += 1
		# Recheck the boundary independently of the database query.
		reason, existing = get_skip_reason(gl, run, currency, sources, voucher_blocks, allowed_types)
		if not reason:
			voucher = frappe.get_doc(gl.voucher_type, gl.voucher_no)
			voucher.check_permission("read")
			if voucher.docstatus != 1:
				reason = "Source voucher is not submitted"
		result = {
			"gl_entry": gl.name,
			"bank_account": bank.name,
			"voucher_type": gl.voucher_type,
			"voucher_no": gl.voucher_no,
		}
		if reason:
			counts["skipped_count"] += 1
			log.append(
				{**result, "result": "Skipped", "reason": reason, "existing_bank_transaction": existing}
			)
			continue
		counts["eligible_count"] += 1
		bt = build_transaction(run, bank, gl, voucher, currency)
		if cint(run.dry_run):
			bt.run_method("before_validate")
			bt.run_method("validate")
			log.append(
				{
					**result,
					"date": str(gl.posting_date),
					"currency": currency,
					"deposit": bt.deposit,
					"withdrawal": bt.withdrawal,
					"result": "Eligible (preview only)",
				}
			)
		else:
			bt.insert()
			if bt.docstatus != 0:
				frappe.throw(_("Generated Bank Transactions must remain in draft."))
			counts["created_count"] += 1
			sources[gl.name] = bt.name
			log.append({**result, "bank_transaction": bt.name, "result": "Created draft"})


def get_existing_links(account, exclude=None):
	"""Scope voucher allocations to the bank GL account, not the voucher alone.

	Zero allocations in drafts also reserve a voucher. Tagged sibling GL rows
	remain independently eligible; an untagged allocation blocks the voucher.
	"""
	bt, ba, payment = (
		frappe.qb.DocType(d) for d in ("Bank Transaction", "Bank Account", "Bank Transaction Payments")
	)
	base = (
		frappe.qb.from_(bt)
		.join(ba)
		.on(ba.name == bt.bank_account)
		.where(ba.account == account)
		.where(bt.docstatus < 2)
	)
	if exclude:
		base = base.where(bt.name != exclude)
	source_rows = base.select(bt.name, bt.custom_source_gl_entry).run(as_dict=True)
	allocations = (
		base.join(payment)
		.on(payment.parent == bt.name)
		.select(bt.name, bt.custom_source_gl_entry, payment.payment_document, payment.payment_entry)
	).run(as_dict=True)
	sources = {r.custom_source_gl_entry: r.name for r in source_rows if r.custom_source_gl_entry}
	blocks = {
		(r.payment_document, r.payment_entry): r.name for r in allocations if not r.custom_source_gl_entry
	}
	return sources, blocks


def get_skip_reason(gl, run, currency, sources, blocks, allowed_types):
	if getdate(gl.posting_date) > getdate(run.cutoff_date):
		return "GL Entry is beyond the cut-off date", None
	if run.from_date and getdate(gl.posting_date) < getdate(run.from_date):
		return "GL Entry is before From Date", None
	if gl.name in sources:
		return "Source GL Entry is already linked to an active Bank Transaction", sources[gl.name]
	key = (gl.voucher_type, gl.voucher_no)
	if key in blocks:
		return (
			"Source voucher already linked/allocated without GL Entry identification on this bank GL account",
			blocks[key],
		)
	if gl.is_opening == "Yes":
		return "Opening GL entry; not an actual bank movement", None
	if gl.voucher_type not in allowed_types:
		return "Voucher type does not support standard bank reconciliation", None
	if gl.account_currency != currency:
		return "GL currency differs from the bank account currency", None
	debit, credit = flt(gl.debit_in_account_currency), flt(gl.credit_in_account_currency)
	if not ((debit > 0 and credit == 0) or (credit > 0 and debit == 0)):
		return "GL row must have exactly one positive debit or credit", None
	return None, None


def build_transaction(run, bank, gl, voucher, currency):
	return frappe.get_doc(
		{
			"doctype": "Bank Transaction",
			"docstatus": 0,
			"company": run.company,
			"bank_account": bank.name,
			"date": gl.posting_date,
			"currency": currency,
			"deposit": flt(gl.debit_in_account_currency),
			"withdrawal": flt(gl.credit_in_account_currency),
			"description": gl.remarks or f"Generated from {gl.voucher_type} {gl.voucher_no} / GL {gl.name}",
			"reference_number": voucher.get("reference_no") or voucher.get("cheque_no") or gl.voucher_no,
			"party_type": gl.party_type,
			"party": gl.party,
			"custom_source_gl_entry": gl.name,
			"custom_gl_generation_run": run.name,
			"custom_active_gl_key": gl.name,
			"payment_entries": [
				{"payment_document": gl.voucher_type, "payment_entry": gl.voucher_no, "allocated_amount": 0}
			],
		}
	)


def require_live_generation(doc, method=None):
	if not doc.get("custom_source_gl_entry"):
		return
	run = frappe.get_doc(RUN_DOCTYPE, doc.custom_gl_generation_run)
	if cint(run.dry_run) or run.status != "Running" or run.requested_by != frappe.session.user:
		frappe.throw(
			_("Generated drafts may only be inserted by the requester during a live generation run.")
		)
	if doc.docstatus != 0:
		frappe.throw(_("Generated Bank Transactions must be created as drafts."))


def validate_source(doc, method=None):
	source = doc.get("custom_source_gl_entry")
	previous = doc.get_value_before_save("custom_source_gl_entry") if not doc.is_new() else None
	if previous and source != previous:
		frappe.throw(
			_("Source GL Entry cannot be changed. Delete the draft or cancel it to release its source.")
		)
	if not source:
		doc.custom_active_gl_key = None
		return
	gl = frappe.get_doc("GL Entry", source)
	gl.check_permission("read")
	bank = frappe.get_doc("Bank Account", doc.bank_account)
	bank.check_permission("read")
	if gl.is_cancelled or gl.is_opening == "Yes":
		frappe.throw(_("Source GL Entry is cancelled or is an opening entry."))
	if bank.account != gl.account or bank.company != gl.company or doc.company != gl.company:
		frappe.throw(_("Company and bank account must match the source GL Entry."))
	if getdate(doc.date) != getdate(gl.posting_date) or doc.currency != gl.account_currency:
		frappe.throw(_("Date and currency must match the source GL Entry."))
	for field, gl_field in (
		("deposit", "debit_in_account_currency"),
		("withdrawal", "credit_in_account_currency"),
	):
		if flt(doc.get(field), doc.precision(field)) != flt(gl.get(gl_field), doc.precision(field)):
			frappe.throw(_("Amounts must match the individual source GL Entry."))
	if not doc.get("custom_gl_generation_run"):
		frappe.throw(_("GL Generation Run is required."))
	run = frappe.get_doc(RUN_DOCTYPE, doc.custom_gl_generation_run)
	if run.company != gl.company or (run.bank_account and run.bank_account != doc.bank_account):
		frappe.throw(_("Company and bank account differ from the generation request."))
	if len(doc.payment_entries) != 1 or (
		doc.payment_entries[0].payment_document,
		doc.payment_entries[0].payment_entry,
	) != (gl.voucher_type, gl.voucher_no):
		frappe.throw(_("Keep exactly the original source voucher linked to this generated transaction."))
	voucher = frappe.get_doc(gl.voucher_type, gl.voucher_no)
	voucher.check_permission("read")
	if voucher.docstatus != 1:
		frappe.throw(_("The source voucher must remain submitted."))
	sources, blocks = get_existing_links(gl.account, exclude=doc.name)
	reason, existing = get_skip_reason(
		gl, run, doc.currency, sources, blocks, frappe.get_hooks("bank_reconciliation_doctypes")
	)
	if reason:
		frappe.throw(_("{0}. {1}").format(reason, existing or ""))
	doc.custom_active_gl_key = source
	if doc.docstatus == 0:
		doc.payment_entries[0].allocated_amount = 0
		doc.allocated_amount = 0
		doc.unallocated_amount = abs(flt(doc.deposit) - flt(doc.withdrawal))


def release_source(doc, method=None):
	if doc.get("custom_source_gl_entry"):
		doc.custom_active_gl_key = None
