# Copyright (c) 2013, Aakvatech Limited and contributors
# For license information, please see license.txt


import frappe
from frappe import _, scrub
from frappe.utils import getdate, nowdate
from frappe.query_builder.functions import Coalesce
from pypika.terms import ExistsCriterion


class PartyLedgerSummaryReport:
	def __init__(self, filters=None):
		self.filters = frappe._dict(filters or {})
		self.filters.from_date = getdate(self.filters.from_date or nowdate())
		self.filters.to_date = getdate(self.filters.to_date or nowdate())

		if not self.filters.get("company"):
			self.filters["company"] = frappe.db.get_single_value("Global Defaults", "default_company")

	def run(self, args):
		if self.filters.from_date > self.filters.to_date:
			frappe.throw(_("From Date must be before To Date"))

		self.filters.party_type = args.get("party_type")
		self.party_naming_by = frappe.db.get_single_value(args.get("naming_by")[0], args.get("naming_by")[1])

		self.get_gl_entries()
		self.get_return_invoices()
		self.get_party_adjustment_amounts()

		columns = self.get_columns()
		data = self.get_data()
		return columns, data

	def get_columns(self):
		columns = [
			{
				"label": _(self.filters.party_type),
				"fieldtype": "Link",
				"fieldname": "party",
				"options": self.filters.party_type,
				"width": 200,
			}
		]

		if self.party_naming_by == "Naming Series":
			columns.append(
				{
					"label": _(self.filters.party_type + "Name"),
					"fieldtype": "Data",
					"fieldname": "party_name",
					"width": 110,
				}
			)

		credit_or_debit_note = "Credit Note" if self.filters.party_type == "Customer" else "Debit Note"

		columns += [
			{
				"label": _("Opening Balance"),
				"fieldname": "opening_balance",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Invoiced Amount"),
				"fieldname": "invoiced_amount",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Paid Amount"),
				"fieldname": "paid_amount",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _(credit_or_debit_note),
				"fieldname": "return_amount",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
		]

		for account in self.party_adjustment_accounts:
			columns.append(
				{
					"label": account,
					"fieldname": "adj_" + scrub(account),
					"fieldtype": "Currency",
					"options": "currency",
					"width": 120,
					"is_adjustment": 1,
				}
			)

		columns += [
			{
				"label": _("Closing Balance"),
				"fieldname": "closing_balance",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Currency"),
				"fieldname": "currency",
				"fieldtype": "Link",
				"options": "Currency",
				"width": 50,
			},
		]

		return columns

	def get_data(self):
		invoice_dr_or_cr = (
			"debit_in_account_currency"
			if self.filters.party_type == "Customer"
			else "credit_in_account_currency"
		)
		reverse_dr_or_cr = (
			"credit_in_account_currency"
			if self.filters.party_type == "Customer"
			else "debit_in_account_currency"
		)

		self.party_data = frappe._dict({})
		for gle in self.gl_entries:
			self.party_data.setdefault(
				gle.party,
				frappe._dict(
					{
						"party": gle.party,
						"party_name": gle.party_name,
						"opening_balance": 0,
						"invoiced_amount": 0,
						"paid_amount": 0,
						"return_amount": 0,
						"closing_balance": 0,
						"currency": gle.account_currency,
					}
				),
			)

			amount = gle.get(invoice_dr_or_cr) - gle.get(reverse_dr_or_cr)
			self.party_data[gle.party].closing_balance += amount

			if gle.posting_date < self.filters.from_date or gle.is_opening == "Yes":
				self.party_data[gle.party].opening_balance += amount
			else:
				if amount > 0:
					self.party_data[gle.party].invoiced_amount += amount
				elif gle.voucher_no in self.return_invoices:
					self.party_data[gle.party].return_amount -= amount
				else:
					self.party_data[gle.party].paid_amount -= amount

		out = []
		for party, row in self.party_data.items():
			if (
				row.opening_balance
				or row.invoiced_amount
				or row.paid_amount
				or row.return_amount
				or row.closing_amount
			):
				total_party_adjustment = sum(
					amount for amount in self.party_adjustment_details.get(party, {}).values()
				)
				row.paid_amount -= total_party_adjustment

				adjustments = self.party_adjustment_details.get(party, {})
				for account in self.party_adjustment_accounts:
					row["adj_" + scrub(account)] = adjustments.get(account, 0)

				out.append(row)

		return out

	def _party_condition(self, gle):
		condition = (
			(gle.docstatus < 2)
			& (gle.is_cancelled == 0)
			& (gle.party_type == self.filters.party_type)
			& (Coalesce(gle.party, "") != "")
			& (gle.posting_date <= self.filters.to_date)
		)
		if self.filters.company:
			condition &= gle.company == self.filters.company
		if self.filters.finance_book:
			condition &= Coalesce(gle.finance_book, "").isin([self.filters.finance_book, ""])
		if self.filters.get("party"):
			condition &= gle.party == self.filters.party

		if self.filters.party_type == "Customer":
			customer = frappe.qb.DocType("Customer")
			if self.filters.get("customer_group"):
				group = frappe.qb.DocType("Customer Group")
				lft, rgt = frappe.db.get_value("Customer Group", self.filters.customer_group, ["lft", "rgt"])
				members = frappe.qb.from_(customer).join(group).on(group.name == customer.customer_group).select(customer.name).where((group.lft >= lft) & (group.rgt <= rgt))
				condition &= gle.party.isin(members)
			if self.filters.get("territory"):
				territory = frappe.qb.DocType("Territory")
				lft, rgt = frappe.db.get_value("Territory", self.filters.territory, ["lft", "rgt"])
				members = frappe.qb.from_(customer).join(territory).on(territory.name == customer.territory).select(customer.name).where((territory.lft >= lft) & (territory.rgt <= rgt))
				condition &= gle.party.isin(members)
			if self.filters.get("payment_terms_template"):
				members = frappe.qb.from_(customer).select(customer.name).where(customer.payment_terms == self.filters.payment_terms_template)
				condition &= gle.party.isin(members)
			if self.filters.get("sales_partner"):
				members = frappe.qb.from_(customer).select(customer.name).where(customer.default_sales_partner == self.filters.sales_partner)
				condition &= gle.party.isin(members)
			if self.filters.get("sales_person"):
				sales_team = frappe.qb.DocType("Sales Team")
				sales_person = frappe.qb.DocType("Sales Person")
				lft, rgt = frappe.db.get_value("Sales Person", self.filters.sales_person, ["lft", "rgt"])
				member_names = frappe.qb.from_(sales_person).select(sales_person.name).where((sales_person.lft >= lft) & (sales_person.rgt <= rgt))
				matching = (
					frappe.qb.from_(sales_team).select(sales_team.name)
					.where(sales_team.sales_person.isin(member_names))
					.where(
						((sales_team.parent == gle.voucher_no) & (sales_team.parenttype == gle.voucher_type))
						| ((sales_team.parent == gle.against_voucher) & (sales_team.parenttype == gle.against_voucher_type))
						| ((sales_team.parent == gle.party) & (sales_team.parenttype == "Customer"))
					)
				)
				condition &= ExistsCriterion(matching)
		elif self.filters.party_type == "Supplier" and self.filters.get("supplier_group"):
			supplier = frappe.qb.DocType("Supplier")
			members = frappe.qb.from_(supplier).select(supplier.name).where(supplier.supplier_group == self.filters.supplier_group)
			condition &= gle.party.isin(members)
		return condition

	def get_gl_entries(self):
		gle = frappe.qb.DocType("GL Entry")
		query = frappe.qb.from_(gle)
		fields = [
			gle.posting_date, gle.party, gle.voucher_type, gle.voucher_no,
			gle.against_voucher_type, gle.against_voucher, gle.debit, gle.credit,
			gle.is_opening, gle.debit_in_account_currency,
			gle.credit_in_account_currency, gle.account_currency,
		]
		if self.filters.party_type in ("Customer", "Supplier"):
			party = frappe.qb.DocType(self.filters.party_type)
			name_field = "customer_name" if self.filters.party_type == "Customer" else "supplier_name"
			query = query.left_join(party).on(gle.party == party.name)
			fields.append(party[name_field].as_("party_name"))
		self.gl_entries = (
			query.select(*fields)
			.where(self._party_condition(gle))
			.orderby(gle.posting_date)
		).run(as_dict=True)


	def get_return_invoices(self):
		doctype = "Sales Invoice" if self.filters.party_type == "Customer" else "Purchase Invoice"
		self.return_invoices = [
			d.name
			for d in frappe.get_all(
				doctype,
				filters={
					"is_return": 1,
					"docstatus": 1,
					"posting_date": ["between", [self.filters.from_date, self.filters.to_date]],
				},
			)
		]

	def get_party_adjustment_amounts(self):
		income_or_expense = "Expense Account" if self.filters.party_type == "Customer" else "Income Account"
		invoice_dr_or_cr = "debit_in_account_currency" if self.filters.party_type == "Customer" else "credit_in_account_currency"
		reverse_dr_or_cr = "credit_in_account_currency" if self.filters.party_type == "Customer" else "debit_in_account_currency"
		round_off_account = frappe.get_cached_value("Company", self.filters.company, "round_off_account")

		gl = frappe.qb.DocType("GL Entry")
		expense_gl = frappe.qb.DocType("GL Entry", alias="expense_gl")
		party_gl = frappe.qb.DocType("GL Entry", alias="party_gl")
		account = frappe.qb.DocType("Account")
		expense_vouchers = (
			frappe.qb.from_(expense_gl)
			.join(account).on(account.name == expense_gl.account)
			.select(expense_gl.voucher_type, expense_gl.voucher_no)
			.where(
				(account.account_type == income_or_expense)
				& expense_gl.posting_date.between(self.filters.from_date, self.filters.to_date)
				& (expense_gl.docstatus < 2)
			)
			.distinct()
		)
		party_vouchers = (
			frappe.qb.from_(party_gl)
			.select(party_gl.voucher_type, party_gl.voucher_no)
			.where(
				self._party_condition(party_gl)
				& party_gl.posting_date.between(self.filters.from_date, self.filters.to_date)
			)
			.distinct()
		)
		# Preserve matching by BOTH voucher type and voucher number.
		from pypika.terms import Tuple
		voucher_key = Tuple(gl.voucher_type, gl.voucher_no)
		gl_entries = (
			frappe.qb.from_(gl)
			.select(
				gl.posting_date, gl.account, gl.party, gl.voucher_type, gl.voucher_no,
				gl.debit_in_account_currency, gl.credit_in_account_currency,
			)
			.where((gl.docstatus < 2) & (gl.is_cancelled == 0))
			.where(voucher_key.isin(expense_vouchers) & voucher_key.isin(party_vouchers))
		).run(as_dict=True)

		self.party_adjustment_details = {}
		self.party_adjustment_accounts = set()
		adjustment_voucher_entries = {}
		for gle in gl_entries:
			adjustment_voucher_entries.setdefault((gle.voucher_type, gle.voucher_no), [])
			adjustment_voucher_entries[(gle.voucher_type, gle.voucher_no)].append(gle)

		for voucher_gl_entries in adjustment_voucher_entries.values():
			parties = {}
			accounts = {}
			has_irrelevant_entry = False

			for gle in voucher_gl_entries:
				if gle.account == round_off_account:
					continue
				elif gle.party:
					parties.setdefault(gle.party, 0)
					parties[gle.party] += gle.get(reverse_dr_or_cr) - gle.get(invoice_dr_or_cr)
				elif frappe.get_cached_value("Account", gle.account, "account_type") == income_or_expense:
					accounts.setdefault(gle.account, 0)
					accounts[gle.account] += gle.get(invoice_dr_or_cr) - gle.get(reverse_dr_or_cr)
				else:
					has_irrelevant_entry = True

			if parties and accounts:
				if len(parties) == 1:
					party = next(iter(parties.keys()))
					for account, amount in accounts.items():
						self.party_adjustment_accounts.add(account)
						self.party_adjustment_details.setdefault(party, {})
						self.party_adjustment_details[party].setdefault(account, 0)
						self.party_adjustment_details[party][account] += amount
				elif len(accounts) == 1 and not has_irrelevant_entry:
					account = next(iter(accounts.keys()))
					self.party_adjustment_accounts.add(account)
					for party, amount in parties.items():
						self.party_adjustment_details.setdefault(party, {})
						self.party_adjustment_details[party].setdefault(account, 0)
						self.party_adjustment_details[party][account] += amount


def execute(filters=None):
	args = {
		"party_type": "Customer",
		"naming_by": ["Selling Settings", "cust_master_name"],
	}
	return PartyLedgerSummaryReport(filters).run(args)
