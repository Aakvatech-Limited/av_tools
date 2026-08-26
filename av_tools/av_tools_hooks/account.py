import frappe
from frappe import _


def _is_feature_enabled():
	return bool(frappe.db.get_single_value("AV Tools Settings", "enable_indirect_expense_item_creation"))


def create_indirect_expense_item(doc, method=None):
	if not _is_feature_enabled():
		return

	if frappe.local.flags.ignore_root_company_validation:
		return

	is_income = doc.root_type == "Income"
	is_expense = doc.root_type == "Expense"

	if not doc.company or doc.is_group or not (is_income or is_expense):
		return

	if not check_expenses_in_parent_accounts(doc.name):
		# Unlink the item if it was moved out of Indirect Expenses/Income
		if doc.item:
			doc.item = ""
		return

	item_group_name = "Indirect Income" if is_income else "Indirect Expenses"
	if not frappe.db.exists("Item Group", item_group_name):
		ig = frappe.get_doc(
			doctype="Item Group",
			item_group_name=item_group_name,
		)
		ig.flags.ignore_permissions = True
		frappe.flags.ignore_account_permission = True
		ig.save()

	item = frappe.db.exists("Item", doc.account_name)
	if item:
		item = frappe.get_doc("Item", doc.account_name)
		doc.item = item.name

		if is_income:
			item.is_sales_item = 1
		elif is_expense:
			item.is_purchase_item = 1

		company_list = []
		for i in item.item_defaults:
			if doc.company not in company_list:
				if i.company == doc.company:
					company_list.append(doc.company)
					if is_expense and i.expense_account != doc.name:
						i.expense_account = doc.name
						item.save()
					elif is_income and i.income_account != doc.name:
						i.income_account = doc.name
						item.save()
		if doc.company not in company_list:
			row = item.append("item_defaults", {})
			row.company = doc.company
			if is_expense:
				row.expense_account = doc.name
			elif is_income:
				row.income_account = doc.name
			item.save()
			company_list.append(doc.company)
			doc.db_update()
		return item.name

	new_item = frappe.get_doc(
		doctype="Item",
		item_code=doc.account_name,
		item_group=item_group_name,
		is_stock_item=0,
		is_sales_item=1 if is_income else 0,
		is_purchase_item=1 if is_expense else 0,
		stock_uom="Nos",
		include_item_in_manufacturing=0,
		item_defaults=[
			{
				"company": doc.company,
				"expense_account": doc.name if is_expense else "",
				"income_account": doc.name if is_income else "",
				"default_warehouse": "",
			}
		],
	)
	new_item.flags.ignore_permissions = True
	frappe.flags.ignore_account_permission = True
	new_item.save()
	if new_item.name:
		url = frappe.utils.get_url_to_form(new_item.doctype, new_item.name)
		msgprint = f"New Item is Created <a href='{url}'>{new_item.name}</a>"
		frappe.msgprint(_(msgprint))
		doc.item = new_item.name
	doc.db_update()
	return new_item.name


def check_expenses_in_parent_accounts(account_name):
	parent_account_1 = frappe.get_value("Account", account_name, "parent_account")
	if "Indirect Expenses" in str(parent_account_1) or "Indirect Income" in str(parent_account_1):
		return True
	parent_account_2 = frappe.get_value("Account", parent_account_1, "parent_account")
	if "Indirect Expenses" in str(parent_account_2) or "Indirect Income" in str(parent_account_2):
		return True
	parent_account_3 = frappe.get_value("Account", parent_account_2, "parent_account")
	if "Indirect Expenses" in str(parent_account_3) or "Indirect Income" in str(parent_account_3):
		return True
	return False


@frappe.whitelist()
def add_indirect_expense_item(account_name: str):
	if not _is_feature_enabled():
		frappe.throw(
			_("Indirect Expense/Income Item auto-creation is disabled. Enable it in AV Tools Settings.")
		)
	account = frappe.get_doc("Account", account_name)
	return create_indirect_expense_item(account)
