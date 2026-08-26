// Copyright (c) 2020, Aakvatech and contributors
// For license information, please see license.txt

frappe.provide("erpnext.accounts");

frappe.ui.form.on("Payment Reconciliation Pro Payment", {
	invoice_number: function (frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (row.invoice_number) {
			var parts = row.invoice_number.split(" | ");
			var invoice_type = parts[0];
			var invoice_number = parts[1];

			var invoice_amount = frm.doc.invoices.filter(function (d) {
				return d.invoice_type === invoice_type && d.invoice_number === invoice_number;
			})[0].outstanding_amount;

			frappe.model.set_value(
				cdt,
				cdn,
				"allocated_amount",
				Math.min(invoice_amount, row.amount)
			);

			frm.call({
				doc: frm.doc,
				method: "get_difference_amount",
				args: {
					child_row: row,
				},
				callback: function (r, rt) {
					if (r.message) {
						frappe.model.set_value(cdt, cdn, "difference_amount", r.message);
					}
				},
			});
		}
	},
});

function check_mandatory(frm, only_company = false) {
	const title = __("Mandatory");
	if (only_company && !frm.doc.company) {
		frappe.throw({ message: __("Please Select a Company First"), title: title });
	} else if (!only_company && (!frm.doc.company || !frm.doc.party_type)) {
		frappe.throw({
			message: __("Please Select Both Company and Party Type First"),
			title: title,
		});
	}
}

function toggle_primary_action(frm) {
	const has_payments = (frm.doc.payments || []).length > 0;
	const reconcile = frm.fields_dict.reconcile && frm.fields_dict.reconcile.$input;
	const fetch =
		frm.fields_dict.get_unreconciled_entries &&
		frm.fields_dict.get_unreconciled_entries.$input;
	reconcile && reconcile.toggleClass("btn-primary", has_payments);
	fetch && fetch.toggleClass("btn-primary", !has_payments);
}

function set_invoice_options(frm) {
	const invoices = [];
	(frm.doc.invoices || []).forEach((row) => {
		if (row.invoice_number && !invoices.includes(row.invoice_number))
			invoices.push(row.invoice_type + " | " + row.invoice_number);
	});

	if (invoices) {
		frappe.meta.get_docfield(
			"Payment Reconciliation Pro Payment",
			"invoice_number",
			frm.doc.name
		).options = "\n" + invoices.join("\n");
		(frm.doc.payments || []).forEach((p) => {
			if (!invoices.includes(cstr(p.invoice_number))) p.invoice_number = null;
		});
	}
	frm.refresh_field("payments");
}

function reconcile_payment_entries(frm) {
	return frm.call({
		doc: frm.doc,
		method: "reconcile",
		callback: function () {
			set_invoice_options(frm);
			toggle_primary_action(frm);
		},
	});
}

frappe.ui.form.on("Payment Reconciliation Pro", {
	onload: function (frm) {
		frm.set_query("party", function () {
			return {};
		});

		frm.set_query("party_type", function () {
			return { filters: { name: ["in", Object.keys(frappe.boot.party_account_types)] } };
		});

		frm.set_query("receivable_payable_account", function () {
			return {
				filters: {
					company: frm.doc.company,
					is_group: 0,
					account_type: frappe.boot.party_account_types[frm.doc.party_type],
				},
			};
		});

		frm.set_query("bank_cash_account", function () {
			return {
				filters: [
					["Account", "company", "=", frm.doc.company],
					["Account", "is_group", "=", 0],
					["Account", "account_type", "in", ["Bank", "Cash"]],
				],
			};
		});

		frm.set_value("party_type", "");
		frm.set_value("party", "");
		frm.set_value("receivable_payable_account", "");
	},

	refresh: function (frm) {
		frm.disable_save();
		toggle_primary_action(frm);
	},

	onload_post_render: function (frm) {
		toggle_primary_action(frm);
	},

	party: function (frm) {
		if (!frm.doc.receivable_payable_account && frm.doc.party_type && frm.doc.party) {
			return frappe.call({
				method: "erpnext.accounts.party.get_party_account",
				args: {
					company: frm.doc.company,
					party_type: frm.doc.party_type,
					party: frm.doc.party,
				},
				callback: function (r) {
					if (!r.exc && r.message) {
						frm.set_value("receivable_payable_account", r.message);
					}
				},
			});
		}
	},

	get_unreconciled_entries: function (frm) {
		check_mandatory(frm);
		return frm.call({
			doc: frm.doc,
			method: "get_unreconciled_entries",
			callback: function () {
				set_invoice_options(frm);
				toggle_primary_action(frm);
			},
		});
	},

	reconcile: function (frm) {
		const pending = (frm.doc.payments || []).filter(
			(d) => d.difference_amount && !d.difference_account
		);
		if (!pending.length) {
			return reconcile_payment_entries(frm);
		}

		const data = pending.map((d) => ({
			docname: d.name,
			reference_name: d.reference_name,
			difference_amount: d.difference_amount,
			difference_account: d.difference_account,
		}));
		const dialog = new frappe.ui.Dialog({
			title: __("Select Difference Account"),
			fields: [
				{
					fieldname: "payments",
					fieldtype: "Table",
					label: __("Payments"),
					data: data,
					in_place_edit: true,
					get_data: () => data,
					fields: [
						{ fieldtype: "Data", fieldname: "docname", in_list_view: 1, hidden: 1 },
						{
							fieldtype: "Data",
							fieldname: "reference_name",
							label: __("Voucher No"),
							in_list_view: 1,
							read_only: 1,
						},
						{
							fieldtype: "Link",
							options: "Account",
							in_list_view: 1,
							label: __("Difference Account"),
							fieldname: "difference_account",
							reqd: 1,
							get_query: function () {
								return { filters: { company: frm.doc.company, is_group: 0 } };
							},
						},
						{
							fieldtype: "Currency",
							in_list_view: 1,
							label: __("Difference Amount"),
							fieldname: "difference_amount",
							read_only: 1,
						},
					],
				},
			],
			primary_action: function () {
				const args = dialog.get_values()["payments"];
				args.forEach((d) => {
					frappe.model.set_value(
						"Payment Reconciliation Pro Payment",
						d.docname,
						"difference_account",
						d.difference_account
					);
				});
				reconcile_payment_entries(frm);
				dialog.hide();
			},
			primary_action_label: __("Reconcile Entries"),
		});
		dialog.fields_dict.payments.grid.refresh();
		dialog.show();
	},
});
