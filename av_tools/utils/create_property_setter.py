import json
import os

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

folder = "../patches/property_setter/property_setter_json"


def load_json(file):
	CURR_DIR = os.path.abspath(os.path.dirname(__file__))
	json_file_path = os.path.join(CURR_DIR, folder, file)
	with open(json_file_path) as f:
		return json.load(f)


def create_property_setter_from_json(property_setters_obj):
	for property_setter in property_setters_obj:
		doc_type = property_setter.get("doc_type")
		if not doc_type or not frappe.db.exists("DocType", doc_type):
			continue

		for_doctype = property_setter.get("doctype_or_field") == "DocType"

		make_property_setter(
			doctype=doc_type,
			fieldname=property_setter.get("field_name"),
			property=property_setter.get("property"),
			value=property_setter.get("value"),
			property_type=property_setter.get("property_type"),
			for_doctype=for_doctype,
			validate_fields_for_doctype=False,
		)


def execute():
	folder_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), folder)
	if not os.path.isdir(folder_path):
		return

	files = sorted(f for f in os.listdir(folder_path) if f.endswith(".json"))
	for file in files:
		data = load_json(file)
		create_property_setter_from_json(data)
