from __future__ import unicode_literals

import frappe


def total_amount(doc, method):
    grand_total = 0
    for item in doc.items:
        if item.amount and item.applicable_charges:
            item.custom_total_amount = item.amount + item.applicable_charges
        else:
            item.custom_total_amount = 0
        grand_total += item.custom_total_amount or 0
    doc.custom_grand_total = grand_total if doc.items else 0


@frappe.whitelist()
def get_landed_cost_expenses(import_file=None):
    if not import_file:
        return

    je_landed_cost = frappe.db.sql(
        """
        SELECT jea.account AS expense_account, je.title AS description, jea.debit AS amount
        FROM `tabJournal Entry` je
        INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
        WHERE je.import_file = %s
          AND je.docstatus = 1
          AND jea.debit > 0
        """,
        import_file,
        as_dict=1,
    )

    pinv_landed_cost = frappe.db.sql(
        """
        SELECT pii.expense_account AS expense_account, pi.title AS description, pii.base_net_amount AS amount
        FROM `tabPurchase Invoice` pi
        INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
        WHERE pi.import_file = %s
          AND pi.docstatus = 1
        """,
        import_file,
        as_dict=1,
    )

    return je_landed_cost + pinv_landed_cost
