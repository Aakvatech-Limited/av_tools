import frappe


def execute():
	frappe.db.delete(
		"Custom DocPerm",
		filters={
			"parent": ["in", ("DocType", "Patch Log", "Module Def", "Transaction Log")],
			"name": ["!=", "a"],
		},
	)
