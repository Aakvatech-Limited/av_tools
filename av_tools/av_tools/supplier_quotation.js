// AV Tools Settings > "Don't Fetch Rates in Supplier Quotation from Material Request".
// The server blanks the rates when mapping, but selecting a supplier (or changing
// currency / price list) makes ERPNext re-apply the Buying Price List and Pricing
// Rules to every row. Leave rows that came from a Material Request out of those
// calls so their rates stay blank; manually added rows are priced as usual.

frappe.ui.form.on("Supplier Quotation", {
	onload(frm) {
		const controller = frm.cscript;
		if (!controller || controller.__av_skip_mr_rates) return;
		controller.__av_skip_mr_rates = true;

		const get_item_list = controller._get_item_list;
		controller._get_item_list = function (item) {
			const items = get_item_list.call(this, item);
			if (!this.frm.doc.__onload?.av_skip_mr_rates) return items;

			return items.filter((d) => {
				const row = locals[d.doctype]?.[d.child_docname];
				return !row?.material_request;
			});
		};
	},
});
