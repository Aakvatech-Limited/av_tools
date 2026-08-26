# -*- coding: utf-8 -*-
# Copyright (c) 2020, Aakvatech and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from pathlib import Path

from frappe.model.document import Document


class Theme(Document):
	def validate(self):
		theme_path = Path(__file__).resolve().parents[3] / "public" / "css" / "theme.css"
		theme_path.parent.mkdir(parents=True, exist_ok=True)
		theme_path.write_text(self.theme or "", encoding="utf-8")
