# Copyright (c) 2020, Aakvatech and contributors
# For license information, please see license.txt


import frappe
from frappe import _, msgprint
from frappe.model.document import Document
from frappe.query_builder.functions import Coalesce, Sum
from frappe.query_builder.terms import ConstantColumn
from pypika import Case, Order
from frappe.utils import flt, fmt_money, getdate, nowdate

form_grid_templates = {"journal_entries": "templates/form_grid/bank_reconciliation_grid.html"}


class BankClearancePro(Document):
	@frappe.whitelist()
	def get_payment_entries(self):
		frappe.msgprint(_("Getting entries..."), alert=True)
		if not (self.from_date and self.to_date):
			frappe.throw(_("From Date and To Date are Mandatory"))

		if not self.account:
			frappe.throw(_("Account is mandatory to get payment entries"))

		je = frappe.qb.DocType("Journal Entry")
		jea = frappe.qb.DocType("Journal Entry Account")
		pe = frappe.qb.DocType("Payment Entry")
		condition_je = (
			(je.docstatus == 1)
			& (jea.account == self.account)
			& je.posting_date.between(self.from_date, self.to_date)
			& (Coalesce(je.is_opening, "No") == "No")
		)
		condition_pe = (
			((pe.paid_from == self.account) | (pe.paid_to == self.account))
			& (pe.docstatus == 1)
			& pe.posting_date.between(self.from_date, self.to_date)
		)
		if not self.include_reconciled_entries:
			condition_je &= je.clearance_date.isnull() | (je.clearance_date == "0000-00-00")
			condition_pe &= pe.clearance_date.isnull() | (pe.clearance_date == "0000-00-00")
		if self.bank_account:
			condition_pe &= pe.bank_account == self.bank_account

		journal_entries = (
			frappe.qb.from_(je)
			.join(jea).on(jea.parent == je.name)
			.select(
				ConstantColumn("Journal Entry").as_("payment_document"),
				je.name.as_("payment_entry"), je.cheque_no.as_("cheque_number"),
				je.cheque_date, Sum(jea.debit_in_account_currency).as_("debit"),
				Sum(jea.credit_in_account_currency).as_("credit"),
				je.posting_date, jea.against_account, je.clearance_date,
				jea.account_currency,
			)
			.where(condition_je)
			.groupby(jea.account, je.name)
			.orderby(je.posting_date)
			.orderby(je.name, order=Order.desc)
		).run(as_dict=True)

		payment_entries = (
			frappe.qb.from_(pe)
			.select(
				ConstantColumn("Payment Entry").as_("payment_document"),
				pe.name.as_("payment_entry"),
				pe.reference_no.as_("cheque_number"),
				pe.reference_date.as_("cheque_date"),
				Case().when(pe.paid_from == self.account, pe.paid_amount).else_(0).as_("credit"),
				Case().when(pe.paid_from == self.account, 0).else_(pe.received_amount).as_("debit"),
				pe.posting_date,
				Coalesce(pe.party_name, Case().when(pe.paid_from == self.account, pe.paid_to).else_(pe.paid_from)).as_("against_account"),
				pe.clearance_date,
				Case().when(pe.paid_to == self.account, pe.paid_to_account_currency).else_(pe.paid_from_account_currency).as_("account_currency"),
			)
			.where(condition_pe)
			.orderby(pe.posting_date)
			.orderby(pe.name, order=Order.desc)
		).run(as_dict=True)

		pos_sales_invoices, pos_purchase_invoices = [], []
		if self.include_pos_transactions:
			si = frappe.qb.DocType("Sales Invoice")
			sip = frappe.qb.DocType("Sales Invoice Payment")
			pi = frappe.qb.DocType("Purchase Invoice")
			account = frappe.qb.DocType("Account")
			pos_sales_invoices = (
				frappe.qb.from_(sip)
				.join(si).on(sip.parent == si.name)
				.join(account).on(account.name == sip.account)
				.select(
					ConstantColumn("Sales Invoice Payment").as_("payment_document"),
					sip.name.as_("payment_entry"), sip.amount.as_("debit"),
					si.posting_date, si.customer.as_("against_account"),
					sip.clearance_date, account.account_currency,
					ConstantColumn(0).as_("credit"),
				)
				.where((sip.account == self.account) & (si.docstatus == 1) & si.posting_date.between(self.from_date, self.to_date))
				.orderby(si.posting_date).orderby(si.name, order=Order.desc)
			).run(as_dict=True)
			pos_purchase_invoices = (
				frappe.qb.from_(pi)
				.join(account).on(account.name == pi.cash_bank_account)
				.select(
					ConstantColumn("Purchase Invoice").as_("payment_document"),
					pi.name.as_("payment_entry"), pi.paid_amount.as_("credit"),
					pi.posting_date, pi.supplier.as_("against_account"),
					pi.clearance_date, account.account_currency,
					ConstantColumn(0).as_("debit"),
				)
				.where((pi.cash_bank_account == self.account) & (pi.docstatus == 1) & pi.posting_date.between(self.from_date, self.to_date))
				.orderby(pi.posting_date).orderby(pi.name, order=Order.desc)
			).run(as_dict=True)

		entries = sorted(
			list(payment_entries)
			+ list(journal_entries + list(pos_sales_invoices) + list(pos_purchase_invoices)),
			key=lambda k: k["posting_date"] or getdate(nowdate()),
		)
		frappe.msgprint(_("Got " + str(len(entries)) + " entries."), alert=True)

		self.set("payment_entries", [])
		self.total_amount = 0.0

		for d in entries:
			row = self.append("payment_entries", {})

			amount = flt(d.get("debit", 0)) - flt(d.get("credit", 0))
			d.flt_amount = amount

			formatted_amount = fmt_money(abs(amount), 2, d.account_currency)
			d.amount = formatted_amount + " " + (_("Dr") if amount > 0 else _("Cr"))

			d.pop("credit")
			d.pop("debit")
			d.pop("account_currency")
			row.update(d)
			self.total_amount += flt(amount)

	def update_clearance_date(self):
		clearance_date_updated = False
		for d in self.get("payment_entries"):
			if d.clearance_date:
				if not d.payment_document:
					frappe.throw(_("Row #{0}: Payment document is required to complete the transaction"))

				if d.cheque_date and getdate(d.clearance_date) < getdate(d.cheque_date):
					frappe.msgprint(
						_("Row #{0}: Clearance date {1} cannot be before Cheque Date {2}").format(
							d.idx, d.clearance_date, d.cheque_date
						),
						alert=True,
					)
					frappe.throw(
						_("Row #{0}: Clearance date {1} cannot be before Cheque Date {2}").format(
							d.idx, d.clearance_date, d.cheque_date
						)
					)

			if d.clearance_date or self.include_reconciled_entries:
				if not d.clearance_date:
					d.clearance_date = None

				payment_entry = frappe.get_doc(d.payment_document, d.payment_entry)
				payment_entry.db_set("clearance_date", d.clearance_date)

				clearance_date_updated = True

		if clearance_date_updated:
			self.get_payment_entries()
			msgprint(_("Clearance Date updated"))
		else:
			msgprint(_("Clearance Date not mentioned"))
