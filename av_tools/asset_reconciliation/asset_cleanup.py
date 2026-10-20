"""Reviewed Asset cleanup, using normal permissions, cancellation and deletion hooks."""

import hashlib
import json

import frappe
from frappe import _

OWNED_TYPES = {"Asset", "Asset Depreciation Schedule", "Asset Movement", "Journal Entry", "Asset Activity"}
DELETE_ORDER = {
	"Asset Depreciation Schedule": 0,
	"Asset Movement": 1,
	"Journal Entry": 2,
	"Asset Activity": 3,
	"Asset": 4,
}


def incoming(doctype, name):
	from frappe.desk.form.linked_with import get_references_across_doctypes, get_referencing_documents

	# Restrict both metadata discovery and dynamic-link queries to cleanup-owned
	# DocTypes (and their child tables). Unrestricted discovery scans every app
	# and may fail on unrelated virtual or custom Dynamic Link implementations.
	references = get_references_across_doctypes(
		to_doctypes=[doctype], limit_link_doctypes=sorted(OWNED_TYPES)
	)
	result = set()
	ignored = set(frappe.get_hooks("ignore_links_on_delete"))
	for reference in references.get(doctype, []):
		for parenttype, names in (get_referencing_documents(doctype, [name], reference) or {}).items():
			if parenttype in OWNED_TYPES and parenttype not in ignored:
				result.update((parenttype, parent) for parent in names)
	return result


def ownership_problem(doc, asset):
	if doc.doctype == "Asset":
		return None if doc.name == asset.name else "another Asset references this record"
	if doc.get("company") and doc.company != asset.company:
		return "record belongs to another company"
	if doc.doctype in ("Asset Depreciation Schedule", "Asset Activity"):
		return None if doc.asset == asset.name else "record belongs to another Asset"
	if doc.doctype == "Asset Movement":
		if not doc.assets or any(row.asset != asset.name for row in doc.assets):
			return "movement contains other Assets"
		return None
	if doc.doctype == "Journal Entry":
		if doc.voucher_type != "Depreciation Entry" or not doc.accounts:
			return "only Asset-only depreciation Journal Entries can be cleaned up"
		if any(row.reference_type != "Asset" or row.reference_name != asset.name for row in doc.accounts):
			return "depreciation journal is shared or includes unrelated references"
		return None
	return "resolve this linked document separately; it will not be deleted automatically"


def build_plan(asset_name):
	asset = frappe.get_doc("Asset", asset_name)
	asset.check_permission("read")
	asset.check_permission("delete")
	nodes = {}
	blockers = []
	ledger = []
	pending = [("Asset", asset_name)]
	seen = set()
	while pending:
		key = pending.pop()
		if key in seen:
			continue
		seen.add(key)
		doc = frappe.get_doc(*key)
		doc.check_permission("read")
		if key[0] == "GL Entry":
			ledger.append(doc)
			continue
		problem = ownership_problem(doc, asset)
		if problem:
			blockers.append(f"{key[0]} {key[1]}: {problem}")
			continue
		doc.check_permission("delete")
		if doc.docstatus == 1:
			doc.check_permission("cancel")
		nodes[key] = {
			"doctype": doc.doctype,
			"name": doc.name,
			"docstatus": int(doc.docstatus),
			"modified": str(doc.modified),
		}
		pending.extend(incoming(*key) - seen)
		if doc.doctype == "Asset Depreciation Schedule":
			# Include draft and cancelled journals too, even if they no longer
			# have an account reference back to the Asset (ownership still checked).
			pending.extend(
				("Journal Entry", row.journal_entry) for row in doc.depreciation_schedule if row.journal_entry
			)
	if ledger and not frappe.db.get_single_value("Accounts Settings", "delete_linked_ledger_entries"):
		blockers.append(
			"Accounts Settings must permit Delete Linked Ledger Entries for the related transaction cleanup."
		)
	for entry in ledger:
		voucher = (entry.voucher_type, entry.voucher_no)
		if voucher not in nodes or voucher[0] not in ("Asset", "Journal Entry"):
			blockers.append(f"GL Entry {entry.name}: its source transaction is outside this Asset cleanup")
	result = {
		"asset": asset.name,
		"records": sorted(nodes.values(), key=lambda row: (DELETE_ORDER[row["doctype"]], row["name"])),
		"blockers": sorted(set(blockers)),
		"ledger_entries": len(ledger),
		"ledger_records": sorted(
			[
				{"name": entry.name, "modified": str(entry.modified), "is_cancelled": entry.is_cancelled}
				for entry in ledger
			],
			key=lambda row: row["name"],
		),
		"ledger_note": "Related ledger cleanup follows Accounts Settings and ERPNext transaction deletion hooks.",
	}
	result["token"] = plan_token(result)
	return result


def plan_token(plan):
	payload = {key: value for key, value in plan.items() if key != "token"}
	payload["user"] = frappe.session.user
	return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def execute_plan(plan):
	if plan["blockers"]:
		frappe.throw(_("Asset cleanup is blocked: {0}").format("; ".join(plan["blockers"])))
	# Normal operations only: no force, ignore_permissions, direct GL deletion,
	# ignore_links, or commits. Any failure rolls back the complete request.
	for record in sorted(plan["records"], key=lambda row: (row["doctype"], row["name"])):
		frappe.db.get_value(record["doctype"], record["name"], "name", for_update=True)
	current = build_plan(plan["asset"])
	if current["token"] != plan["token"]:
		frappe.throw(_("Linked records changed. Review the cleanup preview again."))
	# Cancel JE first so its native unlink logic removes schedule references.
	# Reload schedules before cancelling, avoiding duplicate cancellation of JEs.
	cancel_order = {"Journal Entry": 0, "Asset Depreciation Schedule": 1, "Asset Movement": 2, "Asset": 3}
	for record in sorted(plan["records"], key=lambda row: (cancel_order.get(row["doctype"], 4), row["name"])):
		doc = frappe.get_doc(record["doctype"], record["name"])
		if doc.docstatus == 1:
			doc.check_permission("cancel")
			if doc.doctype == "Asset Depreciation Schedule":
				if any(
					frappe.db.get_value("Journal Entry", row.journal_entry, "docstatus") == 1
					for row in doc.depreciation_schedule
					if row.journal_entry
				):
					frappe.throw(_("A schedule still has a submitted journal. Review cleanup again."))
				# Supported ERPNext flag: all owned posted journals were already
				# cancelled above. Avoid re-cancelling an already cancelled JE,
				# and allow deletion of an owned draft JE after its schedule.
				doc.flags.should_not_cancel_depreciation_entries = True
			doc.cancel()
	deleted = []
	for record in plan["records"]:
		if record["doctype"] == "Asset":
			# Native cancellation creates additional activity records. They are
			# solely owned by this Asset and are covered by the confirmation.
			for activity in frappe.get_all("Asset Activity", filters={"asset": plan["asset"]}, pluck="name"):
				frappe.delete_doc("Asset Activity", activity, ignore_missing=False)
		frappe.delete_doc(record["doctype"], record["name"], ignore_missing=False)
		deleted.append({"doctype": record["doctype"], "name": record["name"]})
	return deleted


@frappe.whitelist()
@frappe.read_only()
def preview_asset_cleanup(asset):
	return build_plan(asset)


@frappe.whitelist()
@frappe.read_only()
def preview_invoice_cleanup(purchase_invoice):
	doc = frappe.get_doc("Purchase Invoice", purchase_invoice)
	doc.check_permission("read")
	doc.check_permission("cancel")
	names = frappe.get_all("Asset", filters={"av_nta_purchase_invoice": doc.name}, pluck="name")
	plans = [build_plan(name) for name in names]
	return {"assets": names, "blockers": [blocker for plan in plans for blocker in plan["blockers"]]}


@frappe.whitelist(methods=["POST"])
def cancel_and_delete_asset(asset, token, confirm=None):
	if str(confirm) != "1":
		frappe.throw(_("Confirm cancellation and deletion of the listed linked records first."))
	doc = frappe.get_doc("Asset", asset)
	if doc.get("av_nta_purchase_invoice"):
		frappe.db.get_value("Purchase Invoice", doc.av_nta_purchase_invoice, "name", for_update=True)
	frappe.db.get_value("Asset", asset, "name", for_update=True)
	plan = build_plan(asset)
	if token != plan["token"]:
		frappe.throw(_("Linked records changed. Review the cleanup preview again."))
	return {"deleted": execute_plan(plan)}
