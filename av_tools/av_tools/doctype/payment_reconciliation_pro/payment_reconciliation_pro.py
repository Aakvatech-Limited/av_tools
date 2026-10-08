# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt


import erpnext
import frappe
from erpnext.accounts.utils import (
	get_outstanding_invoices,
	reconcile_against_document,
	update_reference_in_payment_entry,
)
from frappe import _, msgprint
from frappe.model.document import Document
from frappe.utils import cint, flt, today
from frappe.query_builder.functions import Coalesce, Sum
from frappe.query_builder.terms import ConstantColumn


class PaymentReconciliationPro(Document):
	@frappe.whitelist()
	def get_unreconciled_entries(self):
		self.get_nonreconciled_payment_entries()
		self.get_invoice_entries()

	def get_nonreconciled_payment_entries(self):
		self.check_mandatory_to_fetch()

		payment_entries = self.get_payment_entries()
		journal_entries = self.get_jv_entries()

		if self.party_type in ["Customer", "Supplier"]:
			dr_or_cr_notes = self.get_dr_or_cr_notes()
		else:
			dr_or_cr_notes = []

		self.add_payment_entries(payment_entries + journal_entries + dr_or_cr_notes)

	def get_payment_entries(self):
		order_doctype = "Sales Order" if self.party_type == "Customer" else "Purchase Order"
		payment_entries = get_advance_payment_entries(
			self.party_type,
			self.party,
			self.receivable_payable_account,
			order_doctype,
			against_all_orders=True,
			limit=self.limit,
		)

		return payment_entries

	def get_jv_entries(self):
		dr_or_cr = (
			"credit_in_account_currency"
			if erpnext.get_party_account_type(self.party_type) == "Receivable"
			else "debit_in_account_currency"
		)

		je = frappe.qb.DocType("Journal Entry")
		account = frappe.qb.DocType("Journal Entry Account")
		amount = account[dr_or_cr]
		reference_is_unallocated = (
			account.reference_type.isnull()
			| (account.reference_type == "")
			| (
				account.reference_type.isin(["Sales Order", "Purchase Order"])
				& account.reference_name.isnotnull()
				& (account.reference_name != "")
			)
		)
		query = (
			frappe.qb.from_(je)
			.join(account).on(je.name == account.parent)
			.select(
				ConstantColumn("Journal Entry").as_("reference_type"),
				je.name.as_("reference_name"), je.posting_date,
				je.remark.as_("remarks"), account.name.as_("reference_row"),
				amount.as_("amount"), account.is_advance,
				account.account_currency.as_("currency"),
			)
			.where(
				(je.docstatus == 1) & (account.docstatus == 1)
				& (account.party_type == self.party_type) & (account.party == self.party)
				& (account.account == self.receivable_payable_account)
				& (amount > 0) & reference_is_unallocated
			)
			.orderby(je.posting_date)
		)
		if self.bank_cash_account:
			query = query.where(
				je.voucher_type.isin(["Debit Note", "Credit Note"])
				| account.against_account.like("%" + self.bank_cash_account + "%")
			)
		if self.limit:
			query = query.limit(cint(self.limit))
		journal_entries = query.run(as_dict=True)

		return list(journal_entries)

	def get_dr_or_cr_notes(self):
		dr_or_cr = (
			"credit_in_account_currency"
			if erpnext.get_party_account_type(self.party_type) == "Receivable"
			else "debit_in_account_currency"
		)

		reconciled_dr_or_cr = (
			"debit_in_account_currency"
			if dr_or_cr == "credit_in_account_currency"
			else "credit_in_account_currency"
		)

		voucher_type = "Sales Invoice" if self.party_type == "Customer" else "Purchase Invoice"

		doc = frappe.qb.DocType(voucher_type)
		gl = frappe.qb.DocType("GL Entry")
		amount = Sum(gl[dr_or_cr]) - Sum(gl[reconciled_dr_or_cr])
		return (
			frappe.qb.from_(doc)
			.join(gl).on((doc.name == gl.against_voucher) | (doc.name == gl.voucher_no))
			.select(
				doc.name.as_("reference_name"),
				ConstantColumn(voucher_type).as_("reference_type"),
				amount.as_("amount"),
				gl.account_currency.as_("currency"),
			)
			.where(
				(doc[frappe.scrub(self.party_type)] == self.party)
				& (doc.is_return == 1) & (Coalesce(doc.return_against, "") == "")
				& (gl.against_voucher_type == voucher_type)
				& (doc.docstatus == 1) & (gl.party == self.party)
				& (gl.party_type == self.party_type)
				& (gl.account == self.receivable_payable_account)
				& (gl.is_cancelled == 0)
			)
			.groupby(doc.name)
			.having(amount > 0)
		).run(as_dict=True)

	def add_payment_entries(self, entries):
		self.set("payments", [])
		for e in entries:
			row = self.append("payments", {})
			row.update(e)

	def get_invoice_entries(self):
		# Fetch JVs, Sales and Purchase Invoices for 'invoices' to reconcile against

		condition = self.check_condition()

		non_reconciled_invoices = get_outstanding_invoices(
			self.party_type, self.party, self.receivable_payable_account, condition=condition
		)

		if self.limit:
			non_reconciled_invoices = non_reconciled_invoices[: self.limit]

		self.add_invoice_entries(non_reconciled_invoices)

	def add_invoice_entries(self, non_reconciled_invoices):
		# Populate 'invoices' with JVs and Invoices to reconcile against
		self.set("invoices", [])

		for e in non_reconciled_invoices:
			ent = self.append("invoices", {})
			ent.invoice_type = e.get("voucher_type")
			ent.invoice_number = e.get("voucher_no")
			ent.invoice_date = e.get("posting_date")
			ent.amount = flt(e.get("invoice_amount"))
			ent.currency = e.get("currency")
			ent.outstanding_amount = e.get("outstanding_amount")

	@frappe.whitelist()
	def reconcile(self, args):
		for e in self.get("payments"):
			e.invoice_type = None
			if e.invoice_number and " | " in e.invoice_number:
				e.invoice_type, e.invoice_number = e.invoice_number.split(" | ")

		self.get_invoice_entries()
		self.validate_invoice()
		dr_or_cr = (
			"credit_in_account_currency"
			if erpnext.get_party_account_type(self.party_type) == "Receivable"
			else "debit_in_account_currency"
		)

		lst = []
		dr_or_cr_notes = []
		for e in self.get("payments"):
			reconciled_entry = []
			if e.invoice_number and e.allocated_amount:
				if e.reference_type in ["Sales Invoice", "Purchase Invoice"]:
					reconciled_entry = dr_or_cr_notes
				else:
					reconciled_entry = lst

				reconciled_entry.append(self.get_payment_details(e, dr_or_cr))

		if lst:
			reconcile_against_document(lst)

		if dr_or_cr_notes:
			reconcile_dr_cr_note(dr_or_cr_notes, self.company)

		msgprint(_("Successfully Reconciled"))
		self.get_unreconciled_entries()

	def get_payment_details(self, row, dr_or_cr):
		return frappe._dict(
			{
				"voucher_type": row.reference_type,
				"voucher_no": row.reference_name,
				"voucher_detail_no": row.reference_row,
				"against_voucher_type": row.invoice_type,
				"against_voucher": row.invoice_number,
				"account": self.receivable_payable_account,
				"party_type": self.party_type,
				"party": self.party,
				"is_advance": row.is_advance,
				"dr_or_cr": dr_or_cr,
				"unadjusted_amount": flt(row.amount),
				"allocated_amount": flt(row.allocated_amount),
				"difference_amount": row.difference_amount,
				"difference_account": row.difference_account,
			}
		)

	@frappe.whitelist()
	def get_difference_amount(self, child_row):
		if child_row.get("reference_type") != "Payment Entry":
			return

		child_row = frappe._dict(child_row)

		if child_row.invoice_number and " | " in child_row.invoice_number:
			child_row.invoice_type, child_row.invoice_number = child_row.invoice_number.split(" | ")

		dr_or_cr = (
			"credit_in_account_currency"
			if erpnext.get_party_account_type(self.party_type) == "Receivable"
			else "debit_in_account_currency"
		)

		row = self.get_payment_details(child_row, dr_or_cr)

		doc = frappe.get_doc(row.voucher_type, row.voucher_no)
		update_reference_in_payment_entry(row, doc, do_not_save=True)

		return doc.difference_amount

	def check_mandatory_to_fetch(self):
		for fieldname in ["company", "party_type", "party", "receivable_payable_account"]:
			if not self.get(fieldname):
				frappe.throw(_("Please select {0} first").format(self.meta.get_label(fieldname)))

	def validate_invoice(self):
		if not self.get("invoices"):
			frappe.throw(_("No records found in the Invoice table"))

		if not self.get("payments"):
			frappe.throw(_("No records found in the Payment table"))

		unreconciled_invoices = frappe._dict()
		for d in self.get("invoices"):
			unreconciled_invoices.setdefault(d.invoice_type, {}).setdefault(
				d.invoice_number, d.outstanding_amount
			)

		invoices_to_reconcile = []
		for p in self.get("payments"):
			if p.invoice_type and p.invoice_number and p.allocated_amount:
				invoices_to_reconcile.append(p.invoice_number)

				if p.invoice_number not in unreconciled_invoices.get(p.invoice_type, {}):
					frappe.throw(
						_("{0}: {1} not found in Invoice Details table").format(
							p.invoice_type, p.invoice_number
						)
					)

				if flt(p.allocated_amount) > flt(p.amount):
					frappe.throw(
						_(
							"Row {0}: Allocated amount {1} must be less than or equals to Payment Entry amount {2}"
						).format(p.idx, p.allocated_amount, p.amount)
					)

				invoice_outstanding = unreconciled_invoices.get(p.invoice_type, {}).get(p.invoice_number)
				if flt(p.allocated_amount) - invoice_outstanding > 0.009:
					frappe.throw(
						_(
							"Row {0}: Allocated amount {1} must be less than or equals to invoice outstanding amount {2}"
						).format(p.idx, p.allocated_amount, invoice_outstanding)
					)

		if not invoices_to_reconcile:
			frappe.throw(
				_("Please select Allocated Amount, Invoice Type and Invoice Number in atleast one row")
			)

	def check_condition(self):
		cond = f" and posting_date >= {frappe.db.escape(self.from_date)}" if self.from_date else ""
		cond += f" and posting_date <= {frappe.db.escape(self.to_date)}" if self.to_date else ""
		dr_or_cr = (
			"debit_in_account_currency"
			if erpnext.get_party_account_type(self.party_type) == "Receivable"
			else "credit_in_account_currency"
		)

		if self.minimum_amount:
			cond += f" and `{dr_or_cr}` >= {flt(self.minimum_amount)}"
		if self.maximum_amount:
			cond += f" and `{dr_or_cr}` <= {flt(self.maximum_amount)}"

		return cond


def reconcile_dr_cr_note(dr_cr_notes, company):
	for d in dr_cr_notes:
		voucher_type = "Credit Note" if d.voucher_type == "Sales Invoice" else "Debit Note"

		reconcile_dr_or_cr = (
			"debit_in_account_currency"
			if d.dr_or_cr == "credit_in_account_currency"
			else "credit_in_account_currency"
		)

		company_currency = erpnext.get_company_currency(company)

		jv = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": voucher_type,
				"posting_date": today(),
				"company": company,
				"multi_currency": 1 if d.currency != company_currency else 0,
				"accounts": [
					{
						"account": d.account,
						"party": d.party,
						"party_type": d.party_type,
						d.dr_or_cr: abs(d.allocated_amount),
						"reference_type": d.against_voucher_type,
						"reference_name": d.against_voucher,
						"cost_center": erpnext.get_default_cost_center(company),
					},
					{
						"account": d.account,
						"party": d.party,
						"party_type": d.party_type,
						reconcile_dr_or_cr: (
							abs(d.allocated_amount)
							if abs(d.unadjusted_amount) > abs(d.allocated_amount)
							else abs(d.unadjusted_amount)
						),
						"reference_type": d.voucher_type,
						"reference_name": d.voucher_no,
						"cost_center": erpnext.get_default_cost_center(company),
					},
				],
			}
		)

		jv.submit()


def get_advance_payment_entries(
	party_type,
	party,
	party_account,
	order_doctype,
	order_list=None,
	include_unallocated=True,
	against_all_orders=False,
	limit=None,
):
	party_account_field = "paid_from" if party_type in ["Customer", "Student"] else "paid_to"
	currency_field = (
		"paid_from_account_currency" if party_type in ["Customer", "Student"] else "paid_to_account_currency"
	)
	payment_type = "Receive" if party_type in ["Customer", "Student"] else "Pay"
	exchange_rate_field = "source_exchange_rate" if payment_type == "Receive" else "target_exchange_rate"

	payment_entries_against_order, unallocated_payment_entries = [], []
	pe = frappe.qb.DocType("Payment Entry")
	ref = frappe.qb.DocType("Payment Entry Reference")
	if order_list or against_all_orders:
		query = (
			frappe.qb.from_(pe)
			.join(ref).on(pe.name == ref.parent)
			.select(
				ConstantColumn("Payment Entry").as_("reference_type"),
				pe.name.as_("reference_name"), pe.remarks,
				ref.allocated_amount.as_("amount"), ref.name.as_("reference_row"),
				ref.reference_name.as_("against_order"), pe.posting_date,
				pe[currency_field].as_("currency"), pe[exchange_rate_field].as_("exchange_rate"),
			)
			.where(
				(pe[party_account_field] == party_account)
				& (pe.payment_type == payment_type)
				& (pe.party_type == party_type)
				& (pe.party == party) & (pe.docstatus == 1)
				& (ref.reference_doctype == order_doctype)
			)
			.orderby(pe.posting_date)
		)
		if order_list:
			query = query.where(ref.reference_name.isin(order_list))
		if limit:
			query = query.limit(cint(limit))
		payment_entries_against_order = query.run(as_dict=True)

	if include_unallocated:
		query = (
			frappe.qb.from_(pe)
			.select(
				ConstantColumn("Payment Entry").as_("reference_type"),
				pe.name.as_("reference_name"), pe.remarks,
				pe.unallocated_amount.as_("amount"),
				pe[exchange_rate_field].as_("exchange_rate"),
			)
			.where(
				(pe[party_account_field] == party_account)
				& (pe.party_type == party_type)
				& (pe.party == party)
				& (pe.payment_type == payment_type)
				& (pe.docstatus == 1)
				& (pe.unallocated_amount > 0)
			)
			.orderby(pe.posting_date)
		)
		if limit:
			query = query.limit(cint(limit))
		unallocated_payment_entries = query.run(as_dict=True)

	return list(payment_entries_against_order) + list(unallocated_payment_entries)
