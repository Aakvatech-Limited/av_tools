import frappe


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = filters.get("company")
	bank_account = filters.get("bank_account")
	if not company or not bank_account:
		frappe.throw("Please select Company and Bank Account.")
	bank = frappe.get_doc("Bank Account", bank_account)
	bank.check_permission("read")
	if bank.company != company or not bank.is_company_account:
		frappe.throw("Select a company bank account belonging to the selected Company.")
	frappe.get_doc("Company", company).check_permission("read")
	time_span = filters.get("time_span") or "This Month"
	today = frappe.utils.today()
	from_date = frappe.utils.get_first_day(today)
	to_date = frappe.utils.get_last_day(today)
	if time_span == "Last Month":
		previous_month = frappe.utils.add_months(today, -1)
		from_date = frappe.utils.get_first_day(previous_month)
		to_date = frappe.utils.get_last_day(previous_month)
	elif time_span == "This Year":
		from_date = str(today)[:4] + "-01-01"
		to_date = str(today)[:4] + "-12-31"
	elif time_span == "Last Year":
		year = frappe.utils.getdate(today).year - 1
		from_date = str(year) + "-01-01"
		to_date = str(year) + "-12-31"
	elif time_span == "Period":
		if not filters.get("from_date") or not filters.get("to_date"):
			frappe.throw("From Date and To Date are required for Period.")
		from_date = filters.get("from_date")
		to_date = filters.get("to_date")
	elif time_span != "This Month":
		frappe.throw("Invalid Time Span.")
	from_date = frappe.utils.getdate(from_date)
	to_date = frappe.utils.getdate(to_date)
	if from_date > to_date:
		frappe.throw("From Date cannot be after To Date.")
	view = filters.get("view") or "Transaction Detail"
	if view not in ["Transaction Detail", "Monthly Summary"]:
		frappe.throw("Invalid View.")
	currency = frappe.db.get_value("Account", bank.account, "account_currency") if bank.account else None
	if not currency:
		currency = frappe.db.get_value("Company", company, "default_currency")
	rows = frappe.get_list(
		"Bank Transaction",
		filters={"docstatus": 1, "company": company, "bank_account": bank_account, "date": ["<=", to_date]},
		fields=[
			"name",
			"date",
			"description",
			"reference_number",
			"transaction_id",
			"deposit",
			"withdrawal",
			"currency",
			"status",
			"party_type",
			"party",
			"bank_party_name",
		],
		order_by="date asc, creation asc, name asc",
		limit_page_length=0,
	)
	opening = 0.0
	period_rows = []
	for row in rows:
		if row.currency and row.currency != currency:
			frappe.throw(
				"Bank Transactions contain a different currency from the bank account. Please correct the source data."
			)
		deposit = frappe.utils.flt(row.deposit)
		withdrawal = frappe.utils.flt(row.withdrawal)
		if frappe.utils.getdate(row.date) < from_date:
			opening = opening + deposit - withdrawal
		else:
			period_rows.append(row)
	money_columns = [
		{
			"fieldname": "deposit",
			"label": "Deposit",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 145,
		},
		{
			"fieldname": "withdrawal",
			"label": "Withdrawal",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 145,
		},
		{
			"fieldname": "net_movement",
			"label": "Net Movement",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 145,
		},
		{
			"fieldname": "balance",
			"label": "Running Balance",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 165,
		},
		{
			"fieldname": "currency",
			"label": "Currency",
			"fieldtype": "Link",
			"options": "Currency",
			"width": 85,
		},
	]
	data = []
	balance = opening
	total_deposit = 0.0
	total_withdrawal = 0.0
	if view == "Transaction Detail":
		columns = [
			{"fieldname": "date", "label": "Date", "fieldtype": "Date", "width": 105},
			{
				"fieldname": "bank_transaction",
				"label": "Bank Transaction",
				"fieldtype": "Link",
				"options": "Bank Transaction",
				"width": 185,
			},
			{"fieldname": "description", "label": "Description", "fieldtype": "Data", "width": 350},
			{"fieldname": "reference_number", "label": "Reference Number", "fieldtype": "Data", "width": 180},
			*money_columns,
			{"fieldname": "transaction_id", "label": "Transaction ID", "fieldtype": "Data", "width": 180},
			{"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 115},
			{"fieldname": "bank_party_name", "label": "Bank Party Name", "fieldtype": "Data", "width": 200},
			{
				"fieldname": "party_type",
				"label": "Party Type",
				"fieldtype": "Link",
				"options": "DocType",
				"width": 110,
			},
			{
				"fieldname": "party",
				"label": "Party",
				"fieldtype": "Dynamic Link",
				"options": "party_type",
				"width": 180,
			},
		]
		data.append(
			{
				"date": from_date,
				"description": "Opening Balance (prior submitted Bank Transactions)",
				"balance": opening,
				"currency": currency,
				"row_type": "Opening",
			}
		)
		for row in period_rows:
			deposit = frappe.utils.flt(row.deposit)
			withdrawal = frappe.utils.flt(row.withdrawal)
			balance = balance + deposit - withdrawal
			total_deposit = total_deposit + deposit
			total_withdrawal = total_withdrawal + withdrawal
			data.append(
				{
					"date": row.date,
					"bank_transaction": row.name,
					"description": row.description,
					"reference_number": row.reference_number,
					"transaction_id": row.transaction_id,
					"status": row.status,
					"bank_party_name": row.bank_party_name,
					"party_type": row.party_type,
					"party": row.party,
					"deposit": deposit,
					"withdrawal": withdrawal,
					"net_movement": deposit - withdrawal,
					"balance": balance,
					"currency": currency,
					"row_type": "Transaction",
				}
			)
		data.append(
			{
				"date": to_date,
				"description": "Period Total / Closing Balance",
				"deposit": total_deposit,
				"withdrawal": total_withdrawal,
				"net_movement": total_deposit - total_withdrawal,
				"balance": balance,
				"currency": currency,
				"row_type": "Closing",
			}
		)
	else:
		columns = [
			{"fieldname": "month", "label": "Month", "fieldtype": "Data", "width": 150},
			{"fieldname": "period_from", "label": "Period From", "fieldtype": "Date", "width": 110},
			{"fieldname": "period_to", "label": "Period To", "fieldtype": "Date", "width": 110},
			{"fieldname": "transaction_count", "label": "Transactions", "fieldtype": "Int", "width": 110},
			{
				"fieldname": "opening_balance",
				"label": "Opening Balance",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 165,
			},
			*money_columns,
		]
		columns[8]["label"] = "Closing Balance"
		months = {}
		for row in period_rows:
			key = str(row.date)[:7]
			if key not in months:
				months[key] = {"deposit": 0.0, "withdrawal": 0.0, "count": 0}
			months[key]["deposit"] = months[key]["deposit"] + frappe.utils.flt(row.deposit)
			months[key]["withdrawal"] = months[key]["withdrawal"] + frappe.utils.flt(row.withdrawal)
			months[key]["count"] = months[key]["count"] + 1
		month_start = frappe.utils.get_first_day(from_date)
		while month_start <= to_date:
			key = str(month_start)[:7]
			values = months.get(key) or {"deposit": 0.0, "withdrawal": 0.0, "count": 0}
			month_opening = balance
			balance = balance + values["deposit"] - values["withdrawal"]
			total_deposit = total_deposit + values["deposit"]
			total_withdrawal = total_withdrawal + values["withdrawal"]
			period_from = month_start
			if period_from < from_date:
				period_from = from_date
			period_to = frappe.utils.get_last_day(month_start)
			if period_to > to_date:
				period_to = to_date
			data.append(
				{
					"month": key,
					"period_from": period_from,
					"period_to": period_to,
					"transaction_count": values["count"],
					"opening_balance": month_opening,
					"deposit": values["deposit"],
					"withdrawal": values["withdrawal"],
					"net_movement": values["deposit"] - values["withdrawal"],
					"balance": balance,
					"currency": currency,
					"row_type": "Month",
				}
			)
			month_start = frappe.utils.add_months(month_start, 1)
		data.append(
			{
				"month": "Period Total",
				"period_from": from_date,
				"period_to": to_date,
				"transaction_count": len(period_rows),
				"opening_balance": opening,
				"deposit": total_deposit,
				"withdrawal": total_withdrawal,
				"net_movement": total_deposit - total_withdrawal,
				"balance": balance,
				"currency": currency,
				"row_type": "Closing",
			}
		)
	return (
		columns,
		data,
		(
			"Submitted Bank Transactions only. Opening balance is earlier deposits less withdrawals; "
			"balances depend on complete imported history. Same-date entries follow creation order."
		),
	)
