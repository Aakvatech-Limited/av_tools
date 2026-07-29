import frappe
from frappe import _


def _is_feature_enabled():
	return bool(
		frappe.db.get_single_value("AV Tools Settings", "enable_indirect_expense_item_creation")
	)


def create_indirect_expense_item(doc, method=None):
	if not _is_feature_enabled():
		return

	if frappe.local.flags.ignore_root_company_validation:
		return

	if (
		not doc.parent_account
		or doc.is_group
		or not check_expenses_in_parent_accounts(doc.name)
		or not doc.company
	):
		return
	if (
		not doc.parent_account
		and not check_expenses_in_parent_accounts(doc.account_name)
		and doc.item
	):
		doc.item = ""
		return
	indirect_expenses_group = frappe.db.exists("Item Group", "Indirect Expenses")
	if not indirect_expenses_group:
		indirect_expenses_group = frappe.get_doc(
			dict(
				doctype="Item Group",
				item_group_name="Indirect Expenses",
			)
		)
		indirect_expenses_group.flags.ignore_permissions = True
		frappe.flags.ignore_account_permission = True
		indirect_expenses_group.save()
	item = frappe.db.exists("Item", doc.account_name)
	if item:
		item = frappe.get_doc("Item", doc.account_name)
		doc.item = item.name
		company_list = []
		for i in item.item_defaults:
			if doc.company not in company_list:
				if i.company == doc.company:
					company_list.append(doc.company)
					if i.expense_account != doc.name:
						i.expense_account = doc.name
						item.save()
		if doc.company not in company_list:
			row = item.append("item_defaults", {})
			row.company = doc.company
			row.expense_account = doc.name
			item.save()
			company_list.append(doc.company)
			doc.db_update()
		return item.name
	new_item = frappe.get_doc(
		dict(
			doctype="Item",
			item_code=doc.account_name,
			item_group="Indirect Expenses",
			is_stock_item=0,
			is_sales_item=0,
			stock_uom="Nos",
			include_item_in_manufacturing=0,
			item_defaults=[
				{
					"company": doc.company,
					"expense_account": doc.name,
					"default_warehouse": "",
				}
			],
		)
	)
	new_item.flags.ignore_permissions = True
	frappe.flags.ignore_account_permission = True
	new_item.save()
	if new_item.name:
		url = frappe.utils.get_url_to_form(new_item.doctype, new_item.name)
		msgprint = "New Item is Created <a href='{0}'>{1}</a>".format(
			url, new_item.name
		)
		frappe.msgprint(_(msgprint))
		doc.item = new_item.name
	doc.db_update()
	return new_item.name


def check_expenses_in_parent_accounts(account_name):
	parent_account_1 = frappe.get_value("Account", account_name, "parent_account")
	if "Indirect Expenses" in str(parent_account_1):
		return True
	parent_account_2 = frappe.get_value("Account", parent_account_1, "parent_account")
	if "Indirect Expenses" in str(parent_account_2):
		return True
	parent_account_3 = frappe.get_value("Account", parent_account_2, "parent_account")
	if "Indirect Expenses" in str(parent_account_3):
		return True
	return False


@frappe.whitelist(methods=["POST"])
def add_indirect_expense_item(account_name):
	if not _is_feature_enabled():
		frappe.throw(
			_("Indirect Expense Item auto-creation is disabled. Enable it in AV Tools Settings.")
		)
	account = frappe.get_doc("Account", account_name)
	return create_indirect_expense_item(account)
