"""Append native Connections without replacing ERPNext or other apps' dashboards."""

from copy import deepcopy

TARGET = "Asset Capitalization Reconciliation"


def extend(data, fieldname):
    data = deepcopy(data or {})
    transactions = data.setdefault("transactions", [])
    if not any(TARGET in group.get("items", []) for group in transactions):
        transactions.append({"label": "Asset Reconciliation", "items": [TARGET]})
    data.setdefault("non_standard_fieldnames", {})[TARGET] = fieldname
    return data


def asset(data):
    return extend(data, "asset")


def purchase_invoice(data):
    return extend(data, "reconciliation_purchase_invoice")


def journal_entry(data):
    return extend(data, "reconciliation_journal_entry")
