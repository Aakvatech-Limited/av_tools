"""Validated long-form fixed-price import; blank rates request fallback."""

import csv
import io

from av_tools.selling_pricing_engine.calculation import number

HEADERS = ("item_code", "warehouse", "rate", "uom", "currency", "tax_basis")


def parse_prices(text, *, currency, max_items=500, precision=6):
	if not isinstance(text, str) or len(text.encode()) > 1_000_000:
		raise ValueError("Paste a CSV smaller than 1 MB")
	reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
	if not reader.fieldnames or set(reader.fieldnames) != set(HEADERS):
		raise ValueError("Use exactly these CSV headers: " + ",".join(HEADERS))
	rows, seen = [], set()
	for line_no, source in enumerate(reader, 2):
		if None in source or any(value is None for value in source.values()):
			raise ValueError(f"CSV line {line_no}: incorrect column count")
		row = {key: value.strip() for key, value in source.items()}
		if not row["item_code"] or not row["uom"]:
			raise ValueError(f"CSV line {line_no}: verified Item Code and UOM are required")
		if row["currency"] != currency or row["tax_basis"] != "Tax Exclusive":
			raise ValueError(f"CSV line {line_no}: use the target currency and Tax Exclusive prices")
		key = row["item_code"], row["warehouse"], row["uom"]
		if key in seen:
			raise ValueError(f"CSV line {line_no}: duplicate Item / Warehouse / UOM")
		seen.add(key)
		rate = number(row["rate"]) if row["rate"] else None
		if rate is not None:
			if rate <= 0:
				raise ValueError(
					f"CSV line {line_no}: zero/negative rates are not selling prices; leave blank for fallback"
				)
			if rate != rate.quantize(number(1).scaleb(-precision)):
				raise ValueError(f"CSV line {line_no}: rate exceeds the configured precision")
		rows.append(
			{
				"item_code": row["item_code"],
				"warehouse": row["warehouse"] or None,
				"uom": row["uom"],
				"fixed_rate": float(rate) if rate is not None else None,
			}
		)
		if len(rows) > max_items:
			raise ValueError(f"Import exceeds the configured limit of {max_items} rows; split the file")
	if not rows:
		raise ValueError("The CSV contains no price rows")
	return rows
