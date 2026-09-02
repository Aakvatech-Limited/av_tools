app_name = "av_tools"
app_title = "Av Tools"
app_publisher = "Aakvatech"
app_description = "Av Tools"
app_email = "info@aakvatech.com"
app_license = "mit"

app_include_js = [
	"/assets/av_tools/js/financial_statements_override.js",
	"/assets/av_tools/js/ai_assist.js",
	"/assets/av_tools/js/parallel_approval.js",
	"av_tools.bundle.js",
]
app_include_css = "/assets/av_tools/css/theme.css"
web_include_css = "/assets/av_tools/css/theme.css"

doctype_js = {
	"Sales Invoice": [
		"weigh_bridge/doctype/sales_invoice_weighbridge_ticket.js",
		"authotp/api/sales_invoice.js",
		"av_tools/sales_invoice.js",
		"av_tools/item_remaining_qty.js",
	],
	"Delivery Note": [
		"weigh_bridge/doctype/delivery_note_weighbridge_ticket.js",
		"av_tools/delivery_note.js",
	],
	"Sales Order": [
		"weigh_bridge/doctype/sales_order_weighbridge_ticket.js",
		"av_tools/sales_order.js",
	],
	"Purchase Order": [
		"weigh_bridge/doctype/purchase_order_weighbridge_ticket.js",
		"av_tools/purchase_order.js",
	],
	"Stock Entry": "av_tools/stock_entry.js",
	"Purchase Invoice": "weigh_bridge/doctype/purchase_invoice_weighbridge_ticket.js",
	"Purchase Receipt": "weigh_bridge/doctype/purchase_receipt_weighbridge_ticket.js",
	"Material Request": "av_tools/material_request.js",
	"Customer": "authotp/api/customer.js",
	"Account": "av_tools/account.js",
}

before_install = "av_tools.install.before_install"
after_install = [
	"av_tools.utils.create_custom_fields.execute",
	"av_tools.utils.create_property_setter.execute",
]
after_migrate = [
	"av_tools.utils.create_custom_fields.execute",
	"av_tools.utils.create_property_setter.execute",
	"av_tools.patches.v1_0.migrate_ai_integration_site_data.execute",
	"av_tools.patches.v1_0.migrate_report_extension_site_data.execute",
]

doc_events = {
	"Sales Invoice": {
		"validate": [
			"av_tools.weigh_bridge.validation.validate_weighbridge_ticket",
			"av_tools.av_tools_hooks.trade_in.validate_trade_in_serial_no_and_batch",
			"av_tools.av_tools_hooks.trade_in.validate_trade_in_sales_percentage",
			"av_tools.av_tools_hooks.item_remaining_qty.validate_items_remaining_qty",
			"av_tools.av_tools_hooks.sales_invoice_payment.validate_payment_allocation",
		],
		"before_submit": "av_tools.authotp.api.sales_invoice.before_submit",
		"on_submit": "av_tools.av_tools_hooks.trade_in.create_trade_in_stock_entry",
		"on_cancel": "av_tools.av_tools_hooks.trade_in.cancel_trade_in_stock_entry",
	},
	"Delivery Note": {"validate": "av_tools.weigh_bridge.validation.validate_weighbridge_ticket"},
	"Sales Order": {"validate": "av_tools.weigh_bridge.validation.validate_weighbridge_ticket"},
	"Purchase Order": {
		"validate": [
			"av_tools.weigh_bridge.validation.validate_weighbridge_ticket",
			"av_tools.av_tools_hooks.purchase_order.target_warehouse_based_price_list",
		]
	},
	"Purchase Invoice": {"validate": "av_tools.weigh_bridge.validation.validate_weighbridge_ticket"},
	"Purchase Receipt": {"validate": "av_tools.weigh_bridge.validation.validate_weighbridge_ticket"},
	"Custom DocPerm": {"validate": "av_tools.av_tools_hooks.custom_docperm.grant_dependant_access"},
	"Account": {
		"on_update": "av_tools.av_tools_hooks.account.create_indirect_expense_item",
		"after_insert": "av_tools.av_tools_hooks.account.create_indirect_expense_item",
	},
	"Notification Log": {
		"after_insert": "av_tools.google_chat_conversations.notification.enqueue_notification_log",
	},
	"*": {
		"validate": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"onload": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"before_insert": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"after_insert": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"before_naming": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"before_change": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"before_update_after_submit": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"before_validate": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"before_save": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"on_update": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"before_submit": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"autoname": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"on_cancel": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"on_trash": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"on_submit": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"on_update_after_submit": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
		"on_change": ["av_tools.av_tools.doctype.visibility.visibility.run_visibility"],
	},
}

scheduler_events = {
	"cron": {
		"0 */6 * * *": [
			"av_tools.av_tools.doctype.parking_bill.parking_bill.check_bills_all_vehicles",
		]
	},
	"daily": [
		"av_tools.av_tools.doctype.visibility.visibility.trigger_daily_alerts",
		"av_tools.compliance.doctype.license_register.license_register.update_license_statuses",
	],
}

override_whitelisted_methods = {
	"frappe.desk.search.search_link": "av_tools.av_tools_hooks.item_search.search_link",
	"frappe.desk.search.search_widget": "av_tools.av_tools_hooks.item_search.search_widget",
	"frappe.desk.query_report.get_script": "av_tools.av_tools_hooks.query_report.get_script",
	"erpnext.buying.doctype.purchase_order.purchase_order.update_status": "av_tools.av_tools_hooks.generic_erp_behavior_overrides.update_purchase_order_status",
	"erpnext.buying.doctype.purchase_order.purchase_order.close_or_unclose_purchase_orders": "av_tools.av_tools_hooks.generic_erp_behavior_overrides.close_or_unclose_purchase_orders",
	"erpnext.stock.doctype.material_request.material_request.update_status": "av_tools.av_tools_hooks.generic_erp_behavior_overrides.update_material_request_status",
	"erpnext.stock.get_item_details.get_item_details": "av_tools.av_tools_hooks.generic_erp_behavior_overrides.get_item_details",
}

# ReportOverride subclasses frappe's own Report; this is the documented hook.
# nosemgrep: frappe-semgrep-rules.rules.override-doctype-class
override_doctype_class = {"Report": "av_tools.av_tools_hooks.report_override.ReportOverride"}
