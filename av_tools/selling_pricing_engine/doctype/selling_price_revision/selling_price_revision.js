frappe.ui.form.on("Selling Price Revision", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Calculate / Recalculate"), async () => {
			if (frm.is_dirty()) await frm.save();
			await frm.call("calculate");
			await frm.reload_doc();
		});
		frm.add_custom_button(__("Import Fixed Prices"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Import Fixed Prices"),
				fields: [
					{
						fieldname: "csv_text",
						fieldtype: "Code",
						label: __("Mapped price CSV"),
						options: "CSV",
						reqd: 1,
						default: "item_code,warehouse,rate,uom,currency,tax_basis\n",
						description: __(
							"Use verified Item Codes and Warehouse names. Currency must match the Price List. Tax basis: Tax Exclusive. Blank rate uses fallback. Dates come from this revision. Import creates a preview; Submit publishes selected rows."
						),
					},
				],
				primary_action_label: __("Preview Import"),
				async primary_action(values) {
					if (frm.is_dirty()) await frm.save();
					await frm.call("import_fixed_prices", { csv_text: values.csv_text });
					dialog.hide();
					await frm.reload_doc();
				},
			});
			dialog.show();
		});
		if (frm.doc.status === "Calculated") {
			frm.dashboard.set_headline(
				__(
					"Review selected rows. Submit publishes their prices. Blocked rows must be resolved or deselected."
				)
			);
		}
	},
});
