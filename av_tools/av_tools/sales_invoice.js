/* global ctrlQ, ctrlI, ctrlU */

// Trade In feature for Sales Invoice (moved from csf_tz)

frappe.require(["/assets/av_tools/js/shortcuts.js"]);

frappe.ui.keys.add_shortcut({
	shortcut: "ctrl+q",
	action: () => {
		ctrlQ("Sales Invoice Item");
	},
	page: this.page,
	description: __("Select Item Warehouse"),
	ignore_inputs: true,
});

frappe.ui.keys.add_shortcut({
	shortcut: "ctrl+i",
	action: () => {
		ctrlI("Sales Invoice Item");
	},
	page: this.page,
	description: __("Select Customer Item Price"),
	ignore_inputs: true,
});

frappe.ui.keys.add_shortcut({
	shortcut: "ctrl+u",
	action: () => {
		ctrlU("Sales Invoice Item");
	},
	page: this.page,
	description: __("Select Item Price"),
	ignore_inputs: true,
});

frappe.ui.form.on("Sales Invoice", {
	refresh: function (frm) {
		frm.trigger("set_trade_in_field_visibility");
		set_sales_invoice_remaining_balance(frm);
	},
	onload: function (frm) {
		frm.trigger("set_trade_in_field_visibility");
		set_sales_invoice_remaining_balance(frm);
	},
	grand_total: (frm) => set_sales_invoice_remaining_balance(frm),
	paid_amount: (frm) => set_sales_invoice_remaining_balance(frm),
	rounded_total: (frm) => set_sales_invoice_remaining_balance(frm),

	set_trade_in_field_visibility: function (frm) {
		// Fetch the Enable Trade In setting from AV Tools Settings
		frappe.db
			.get_single_value("AV Tools Settings", "enable_trade_in")
			.then((enable_trade_in) => {
				// Show or hide the Custom Is Trade-In checkbox based on the setting
				frm.set_df_property("custom_is_trade_in", "hidden", !enable_trade_in);
			});
	},

	custom_is_trade_in: function (frm) {
		if (frm.doc.custom_is_trade_in) {
			frappe.db
				.get_value("Company", frm.doc.company, ["custom_trade_in_control_account"])
				.then((company_res) => {
					const trade_in_account = company_res?.message?.custom_trade_in_control_account;
					if (!trade_in_account)
						frappe.throw(
							__("Trade-In Control Account is not set in Company settings.")
						);

					if (!frm.doc.items.some((item) => item.item_code === "Trade In")) {
						frm.add_child("items", {
							item_code: "Trade In",
							item_name: "Trade In",
							income_account: trade_in_account,
							qty: 1,
							description: "Trade-In",
						});
						frm.refresh_field("items");
					}
				});
		} else {
			frappe.confirm(
				__('Are you sure you want to remove the "Trade In" item?'),
				() => {
					frm.doc.items = frm.doc.items.filter((item) => item.item_code !== "Trade In");
					frm.refresh_field("items");
				},
				() => frm.set_value("custom_is_trade_in", 1)
			);
		}
	},
});

frappe.ui.form.on("Sales Invoice Item", {
	custom_trade_in_qty: function (frm, cdt, cdn) {
		calculate_row_trade_in_value(frm, cdt, cdn);
	},
	custom_trade_in_item: function (frm, cdt, cdn) {
		// Reset serial numbers when item changes
		frappe.model.set_value(cdt, cdn, "custom_trade_in_serial_no", "");
	},
	custom_trade_in_incoming_rate: function (frm, cdt, cdn) {
		calculate_row_trade_in_value(frm, cdt, cdn);
	},
	item_code: function (frm, cdt, cdn) {
		set_trade_in_fields_readonly(frm);
	},
	form_render(frm, cdt, cdn) {
		// Get the current child table row document
		let row = locals[cdt][cdn];

		// Ensure row is defined before calling the function
		if (row) {
			// Check if the item_code is "Trade In"
			if (row.item_code === "Trade In") {
				// Use toggle_reqd to make the UOM field non-mandatory
				cur_frm.fields_dict.items.grid.toggle_reqd("uom", false);
			} else {
				// For non "Trade In" items, make the UOM field mandatory
				cur_frm.fields_dict.items.grid.toggle_reqd("uom", true);
			}
			set_trade_in_fields_readonly(frm, row);
		}
	},
});

// Calculate custom_total_trade_in_value for a specific row in the items child table
function calculate_row_trade_in_value(frm, cdt, cdn) {
	let row = locals[cdt][cdn];

	// Calculate custom_total_trade_in_value as custom_trade_in_qty * custom_trade_in_incoming_rate
	let total_value = (row.custom_trade_in_qty || 0) * (row.custom_trade_in_incoming_rate || 0);
	frappe.model.set_value(cdt, cdn, "custom_total_trade_in_value", total_value);

	// Set rate field as negative
	frappe.model.set_value(cdt, cdn, "rate", total_value * -1);
}

// Function to set trade-in fields read-only based on conditions
function set_trade_in_fields_readonly(frm, row) {
	if (!row || !row.item_code) {
		return; // Exit if row or item_code is not defined
	}

	const readonly_fields = [
		"item_name",
		"rate",
		"posa_special_discount",
		"posa_special_rate",
		"qty",
	];
	const is_trade_in = row.item_code === "Trade In" ? 1 : 0;

	readonly_fields.forEach((fieldname) => {
		frm.fields_dict.items.grid.update_docfield_property(
			fieldname,
			"read_only",
			is_trade_in,
			row.idx
		);
	});

	// Refresh the row to reflect the changes
	frm.refresh_field("items");
}

const sales_invoice_payment_total = (frm) => flt(frm.doc.rounded_total || frm.doc.grand_total);
const sales_invoice_payments = (frm) => frm.doc.payments || [];
const sales_invoice_payment_sum = (frm, ignored_payment) =>
	sales_invoice_payments(frm).reduce(
		(sum, row) =>
			sum + (ignored_payment && row.name === ignored_payment ? 0 : flt(row.amount)),
		0
	);
const sales_invoice_remaining_balance = (frm, ignored_payment) =>
	Math.max(
		sales_invoice_payment_total(frm) - sales_invoice_payment_sum(frm, ignored_payment),
		0
	);

const set_sales_invoice_remaining_balance = (frm) => {
	if (!frm.fields_dict.custom_remaining_balance) return;

	frm.doc.custom_remaining_balance = flt(
		sales_invoice_remaining_balance(frm),
		precision("custom_remaining_balance", frm.doc)
	);
	frm.refresh_field("custom_remaining_balance");
};

const refresh_sales_invoice_payments = (frm) => {
	frm.cscript?.calculate_paid_amount?.();
	set_sales_invoice_remaining_balance(frm);
	frm.refresh_field("payments");
	frm.dirty();
};

const set_sales_invoice_payment_amount = (frm, row, amount) => {
	row.amount = flt(Math.max(amount, 0), precision("amount", row));
	row.base_amount = flt(
		row.amount * flt(frm.doc.conversion_rate || 1),
		precision("base_amount", row)
	);
};

const balance_sales_invoice_payments = (frm, cdt, cdn) => {
	if (frm._setting_sales_invoice_payments) return;

	const row = frappe.get_doc(cdt, cdn);
	const rows = sales_invoice_payments(frm);
	const total = sales_invoice_payment_total(frm);
	if (!row || total <= 0) return;

	const amount_precision = precision("amount", row);
	let overflow = flt(sales_invoice_payment_sum(frm) - total, amount_precision);
	if (overflow <= 0) return refresh_sales_invoice_payments(frm);

	frm._setting_sales_invoice_payments = true;
	rows.filter((payment) => payment.name !== cdn)
		.sort((a, b) => (a.idx > row.idx) - (b.idx > row.idx) || a.idx - b.idx)
		.some((payment) => {
			const amount = flt(payment.amount, amount_precision);
			const deduction = Math.min(amount, overflow);
			if (deduction) {
				set_sales_invoice_payment_amount(frm, payment, amount - deduction);
				overflow = flt(overflow - deduction, amount_precision);
			}
			return !overflow;
		});

	if (overflow > 0) {
		frappe.msgprint(__("Total payment allocation cannot exceed invoice total."));
		set_sales_invoice_payment_amount(frm, row, flt(row.amount) - overflow);
	}

	refresh_sales_invoice_payments(frm);
	frm._setting_sales_invoice_payments = false;
};

frappe.ui.form.on("Sales Invoice Payment", {
	payments_remove(frm) {
		refresh_sales_invoice_payments(frm);
	},
	mode_of_payment(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!flt(row.amount)) {
			set_sales_invoice_payment_amount(frm, row, sales_invoice_remaining_balance(frm, cdn));
		}
		balance_sales_invoice_payments(frm, cdt, cdn);
	},
	amount(frm, cdt, cdn) {
		balance_sales_invoice_payments(frm, cdt, cdn);
	},
});
