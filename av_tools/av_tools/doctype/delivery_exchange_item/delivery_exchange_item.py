# Copyright (c) 2024, Aakvatech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class DeliveryExchangeItem(Document):
    def validate(self):
        msg = ""

        for index, row in enumerate(self.stock_items):
            table_name = self.stock_items[0].parentfield.replace("_", " ").title()
            validate = get_item_details(
                self.ref_doctype, self.ref_docname, item_code=row.item_sold_or_delivered
            )
            if not validate:
                msg += f"In table <b>{table_name}</b>, Row {index + 1}, Item <b>{row.item_sold_or_delivered}</b> does not exist in <b>{self.ref_doctype} {self.ref_docname}</b> </br>"
            item_exchange_rate = frappe.db.get_value(
                "Item Price",
                {
                    "price_list": validate[0].selling_price_list,
                    "item_code": row.item_exchange,
                },
                "price_list_rate",
            )
            if (flt(item_exchange_rate) * flt(row.qty_sold_or_delivered)) != flt(
                row.amount_sold_or_delivered
            ):
                msg += f"In table <b>{table_name}</b>, Row {index + 1}, Amounts for Item {row.item_sold_or_delivered} and {row.item_exchange} do not match at selling rate <b>{validate[0].selling_price_list}</b>"

        for index, row in enumerate(self.non_stock_items):
            table_name = self.non_stock_items[0].parentfield.replace("_", " ").title()
            validate = get_item_details(
                self.ref_doctype, self.ref_docname, item_code=row.item_sold_or_delivered
            )
            if not validate:
                msg += f"In table <b>{table_name}</b>, Row {index + 1}, Item <b>{row.item_sold_or_delivered}</b> does not exist in <b>{self.ref_doctype} {self.ref_docname}</b> </br>"
            item_exchange_rate = frappe.db.get_value(
                "Item Price",
                {
                    "price_list": validate[0].selling_price_list,
                    "item_code": row.item_exchange,
                },
                "price_list_rate",
            )
            if (flt(item_exchange_rate) * flt(row.qty_sold_or_delivered)) != flt(
                row.amount_sold_or_delivered
            ):
                msg += f"In table <b>{table_name}</b>, Row {index + 1}, Amounts for Item {row.item_sold_or_delivered} and {row.item_exchange} do not match at selling rate <b>{validate[0].selling_price_list}"

        if msg:
            frappe.throw(f"{msg}")

    def on_submit(self):
        stock_items = []
        if len(self.stock_items) > 0:
            for row in self.stock_items:
                stock_items.append(
                    {
                        "s_warehouse": row.warehouse,
                        "t_warehouse": "",
                        "item_code": row.item_exchange,
                        "qty": row.qty_sold_or_delivered,
                        "basic_rate": row.rate_sold_or_delivered,
                        "uom": row.uom,
                    }
                )
                stock_items.append(
                    {
                        "s_warehouse": "",
                        "t_warehouse": row.warehouse,
                        "item_code": row.item_sold_or_delivered,
                        "qty": row.qty_sold_or_delivered,
                        "basic_rate": row.rate_sold_or_delivered,
                        "set_basic_rate_manually": 1,
                        "uom": row.uom,
                        "basic_amount": row.amount_sold_or_delivered,
                    }
                )
                doc = frappe.get_doc(
                    {
                        "doctype": "Stock Entry",
                        "company": self.company,
                        "stock_entry_type": "Delivery Exchange",
                        "posting_date": today(),
                        "items": stock_items,
                        # "ref_doctype": self.doctype,
                        # "ref_docname": self.name,
                    }
                )
            doc.insert(ignore_permissions=True)


@frappe.whitelist()
def get_item_details(doctype, doctype_id, item_code=None):
    condition = ""
    if item_code:
        condition += f"AND cdt.item_code = '{item_code}'"

    return frappe.db.sql(
        f"""
			SELECT 
                cdt.item_code, 
                cdt.amount, 
                cdt.warehouse, 
                cdt.qty, 
                cdt.rate, 
                cdt.uom, 
                pdt.selling_price_list, 
                i.is_stock_item
			FROM `tab{doctype}` pdt 
			INNER JOIN `tab{doctype} Item` cdt 
			ON pdt.name = cdt.parent
            INNER JOIN `tabItem` i 
			ON i.name = cdt.item_code
			WHERE pdt.name = '{doctype_id}'
           
			{condition}
		""",
        as_dict=1,
    )
