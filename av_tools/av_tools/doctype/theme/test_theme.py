# -*- coding: utf-8 -*-
# Copyright (c) 2020, Aakvatech and Contributors
# See license.txt
from __future__ import unicode_literals

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestTheme(FrappeTestCase):
	def test_validate_writes_theme_css_to_av_tools_public_path(self):
		doc = frappe.get_doc({"doctype": "Theme", "theme": "body { color: red; }"})

		with patch("av_tools.av_tools.doctype.theme.theme.Path.mkdir") as mock_mkdir, patch(
			"av_tools.av_tools.doctype.theme.theme.Path.write_text"
		) as mock_write_text:
			doc.validate()

		mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
		mock_write_text.assert_called_once_with("body { color: red; }", encoding="utf-8")
