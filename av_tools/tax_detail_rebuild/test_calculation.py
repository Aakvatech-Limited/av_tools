"""Synthetic historical-tax regression cases; no site or client data required."""

import copy
import json
import unittest

from av_tools.tax_detail_rebuild.calculation import CannotRebuild, fingerprint, reconstruct


def invoice():
	return {
		"doctype": "Purchase Invoice",
		"docstatus": 1,
		"company": "Test Company",
		"name": "TEST-INVOICE",
		"posting_date": "2026-01-01",
		"conversion_rate": 1,
		"items": [
			{
				"name": "r1",
				"idx": 1,
				"item_code": "SAME",
				"base_net_amount": 100,
				"item_tax_template": "SAVED-TAXABLE",
				"item_tax_rate": '{"GST Input":15}',
			},
			{
				"name": "r2",
				"idx": 2,
				"item_code": "SAME",
				"base_net_amount": 50,
				"item_tax_template": "SAVED-ZERO",
				"item_tax_rate": '{"GST Input":0}',
			},
		],
		"taxes": [
			{
				"name": "t1",
				"idx": 1,
				"account_head": "GST Input",
				"rate": 15,
				"charge_type": "On Net Total",
				"base_tax_amount_after_discount_amount": 15,
			}
		],
		"item_wise_tax_details": [
			{"item_row": "r1", "tax_row": "t1", "rate": 15, "amount": 15, "taxable_amount": 100},
			{"item_row": "r2", "tax_row": "t1", "rate": 0, "amount": 2, "taxable_amount": 50},
		],
	}


class TestCalculation(unittest.TestCase):
	def test_explicit_zero_with_duplicate_item_codes(self):
		doc = invoice()
		before = copy.deepcopy(doc)
		result = reconstruct(doc)
		self.assertEqual([r["amount"] for r in result["rows"]], [15, 0])
		self.assertTrue(result["changed"])
		self.assertEqual(doc, before)

	def test_already_correct_is_unchanged_and_ignores_generated_ids(self):
		doc = invoice()
		doc["item_wise_tax_details"] = reconstruct(doc)["rows"]
		doc["item_wise_tax_details"][0]["name"] = "GENERATED-ID"
		doc["item_wise_tax_details"].reverse()
		self.assertFalse(reconstruct(doc)["changed"])

	def test_signed_taxable_adjustments(self):
		doc = invoice()
		doc["items"][0]["base_net_amount"] = 2000
		doc["items"].append(
			{
				"name": "r3",
				"idx": 3,
				"base_net_amount": -40,
				"item_tax_template": "SAVED-TAXABLE",
				"item_tax_rate": '{"GST Input":15}',
			}
		)
		doc["taxes"][0]["base_tax_amount_after_discount_amount"] = 294
		self.assertEqual([r["amount"] for r in reconstruct(doc)["rows"]], [300, 0, -6])

	def test_credit_note_negative_tax(self):
		doc = invoice()
		doc["items"][0]["base_net_amount"] = -100
		doc["taxes"][0]["base_tax_amount_after_discount_amount"] = -15
		self.assertEqual(reconstruct(doc)["rows"][0]["amount"], -15)

	def test_base_currency_is_not_converted_again(self):
		doc = invoice()
		doc["conversion_rate"] = 54
		doc["items"][0]["base_net_amount"] = 5400
		doc["taxes"][0]["base_tax_amount_after_discount_amount"] = 810
		self.assertEqual(reconstruct(doc)["rows"][0]["amount"], 810)

	def test_each_tax_account_reconciles_independently(self):
		doc = invoice()
		doc["taxes"].append(
			{
				"name": "t2",
				"idx": 2,
				"account_head": "Levy",
				"rate": 2,
				"charge_type": "On Net Total",
				"base_tax_amount_after_discount_amount": 2,
				"add_deduct_tax": "Deduct",
			}
		)
		for item in doc["items"]:
			rates = json.loads(item["item_tax_rate"])
			rates["Levy"] = 2 if item["name"] == "r1" else 0
			item["item_tax_rate"] = json.dumps(rates)
		result = reconstruct(doc)
		self.assertEqual([r["amount"] for r in result["rows"]], [15, 0, -2, 0])
		self.assertEqual(result["rows"][2]["taxable_amount"], -100)
		doc["taxes"][1]["base_tax_amount_after_discount_amount"] = 4
		with self.assertRaisesRegex(CannotRebuild, "exceeds tolerance"):
			reconstruct(doc)

	def test_limited_rounding_never_moves_tax_to_zero_rate(self):
		doc = invoice()
		doc["taxes"][0]["base_tax_amount_after_discount_amount"] = 15.01
		result = reconstruct(doc)
		self.assertEqual([r["amount"] for r in result["rows"]], [15.01, 0])
		with self.assertRaisesRegex(CannotRebuild, "exceeds tolerance"):
			reconstruct(doc, tolerance=0)

	def test_no_scaling_to_fit_unexplained_difference(self):
		doc = invoice()
		doc["taxes"][0]["base_tax_amount_after_discount_amount"] = 20
		with self.assertRaisesRegex(CannotRebuild, "exceeds tolerance"):
			reconstruct(doc)

	def test_missing_historical_template_rate_blocks(self):
		doc = invoice()
		doc["items"][1]["item_tax_rate"] = "{}"
		with self.assertRaisesRegex(CannotRebuild, "saved account-specific rate is missing"):
			reconstruct(doc)

	def test_untemplated_item_uses_saved_header_rate(self):
		doc = invoice()
		doc["items"][0]["item_tax_template"] = None
		doc["items"][0]["item_tax_rate"] = "{}"
		self.assertEqual(reconstruct(doc)["rows"][0]["amount"], 15)

	def test_unsupported_charge_types_and_discounts_block(self):
		for charge in ("Actual", "On Previous Row Amount", "On Previous Row Total", "On Item Quantity"):
			with self.subTest(charge=charge):
				doc = invoice()
				doc["taxes"][0]["charge_type"] = charge
				with self.assertRaisesRegex(CannotRebuild, "unsupported charge"):
					reconstruct(doc)
		for field in ("discount_amount", "base_discount_amount", "additional_discount_percentage"):
			with self.subTest(field=field):
				doc = invoice()
				doc[field] = 1
				with self.assertRaisesRegex(CannotRebuild, "discounts"):
					reconstruct(doc)

	def test_withholding_and_frozen_tax_are_blocked(self):
		for field in ("is_tax_withholding_account", "dont_recompute_tax"):
			with self.subTest(field=field):
				doc = invoice()
				doc["taxes"][0][field] = 1
				with self.assertRaises(CannotRebuild):
					reconstruct(doc)

	def test_invalid_rates_are_not_coerced_to_zero(self):
		for value in ('{"GST Input":"N/A"}', '{"GST Input":"NaN"}', "[]", "broken"):
			with self.subTest(value=value):
				doc = invoice()
				doc["items"][0]["item_tax_rate"] = value
				with self.assertRaises(CannotRebuild):
					reconstruct(doc)

	def test_draft_cancelled_unsupported_and_duplicate_sources_block(self):
		for status in (0, 2):
			doc = invoice()
			doc["docstatus"] = status
			with self.assertRaises(CannotRebuild):
				reconstruct(doc)
		doc = invoice()
		doc["items"][1]["name"] = "r1"
		with self.assertRaisesRegex(CannotRebuild, "duplicate source item"):
			reconstruct(doc)

	def test_precision_and_tolerance_are_bounded(self):
		for precision, tolerance in ((7, 0.5), (2, 1), (2, -0.01)):
			with self.assertRaises(CannotRebuild):
				reconstruct(invoice(), precision=precision, tolerance=tolerance)
		doc = invoice()
		doc["taxes"][0]["base_tax_amount_after_discount_amount"] = 15.001
		with self.assertRaisesRegex(CannotRebuild, "more decimals"):
			reconstruct(doc)

	def test_fingerprint_covers_source_and_child_changes(self):
		doc = invoice()
		original = fingerprint(doc)
		doc["items"][0]["base_net_amount"] = 110
		self.assertNotEqual(fingerprint(doc), original)
		doc = invoice()
		doc["item_wise_tax_details"][0]["amount"] = 14
		self.assertNotEqual(fingerprint(doc), original)


if __name__ == "__main__":
	unittest.main()
