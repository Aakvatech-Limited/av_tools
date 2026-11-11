frappe.provide("av_tools.selling_pricing_engine");

(() => {
	if (frappe.__selling_pricing_engine_loaded) return;
	frappe.__selling_pricing_engine_loaded = true;

	const api = "av_tools.selling_pricing_engine.sales";
	const configs = new Map();

	const getConfiguration = async (company) => {
		if (!company) return { enabled: false };
		if (!configs.has(company)) {
			try {
				const conf = await frappe.xcall(`${api}.sales_configuration`, { company });
				configs.set(company, conf || { enabled: false });
			} catch (err) {
				console.warn("SPE: Failed to load company pricing configuration", err);
				configs.set(company, { enabled: false });
			}
		}
		return configs.get(company);
	};

	async function refresh(frm) {
		// Only run on draft documents
		if (!frm || !frm.doc || frm.doc.docstatus !== 0) return;

		const config = await getConfiguration(frm.doc.company);
		if (!config || !config.enabled) return;

		const request = (frm.__spe_request || 0) + 1;
		frm.__spe_request = request;

		const getHeaderSnapshot = () => JSON.stringify([
			frm.doc.company,
			frm.doc.selling_price_list,
			frm.doc.currency,
			frm.doc.conversion_rate,
			frm.doc.plc_conversion_rate,
			frm.doc.transaction_date || frm.doc.posting_date,
			frm.doc.custom_spe_keep_manual_rates,
			frm.doc.custom_spe_branch,
		]);

		const header = getHeaderSnapshot();

		let rows = [];
		try {
			rows = await frappe.xcall(`${api}.refresh_prices`, { doc: frm.doc });
		} catch (err) {
			console.warn("SPE: Price refresh skipped or failed on server", err);
			return;
		}

		// Discard stale responses if user continued typing or editing
		if (request !== frm.__spe_request || getHeaderSnapshot() !== header) return;

		if (!Array.isArray(rows) || !rows.length) return;

		for (const result of rows) {
			const row = (frm.doc.items || []).find((item) => item.name === result.name);
			if (
				!row ||
				row.item_code !== result.item_code ||
				row.warehouse !== result.warehouse ||
				row.uom !== result.uom
			) {
				continue;
			}

			await frappe.model.set_value(row.doctype, row.name, {
				price_list_rate: result.price_list_rate,
				rate: result.rate,
				custom_spe_price_source: result.custom_spe_price_source,
				custom_spe_resolved_price_list: result.custom_spe_resolved_price_list,
				custom_spe_resolution: result.custom_spe_resolution,
			});
		}

		await frm.trigger("calculate_taxes_and_totals");
	}

	const schedule = (frm) => {
		if (frm && frm.doc && frm.doc.docstatus === 0) {
			frappe.after_ajax(() => refresh(frm));
		}
	};

	for (const doctype of ["Quotation", "Sales Order", "Sales Invoice"]) {
		frappe.ui.form.on(doctype, {
			async refresh(frm) {
				if (!frm.doc || !frm.doc.company) return;

				configs.delete(frm.doc.company);
				const config = await getConfiguration(frm.doc.company);

				if (frm.fields_dict.custom_spe_keep_manual_rates) {
					frm.toggle_display("custom_spe_keep_manual_rates", !!config.enabled);
				}
				if (frm.fields_dict.custom_spe_branch) {
					frm.toggle_display("custom_spe_branch", !!config.expanded);
				}

				if (config.enabled && frm.doc.docstatus === 0) {
					frm.add_custom_button(__("Refresh Selling Prices"), () => refresh(frm));
				}
			},
			company: schedule,
			customer: schedule,
			party_name: schedule,
			ignore_pricing_rule: schedule,
			selling_price_list: schedule,
			set_warehouse: schedule,
			transaction_date: schedule,
			posting_date: schedule,
			currency: schedule,
			conversion_rate: schedule,
			plc_conversion_rate: schedule,
			custom_spe_keep_manual_rates: schedule,
			custom_spe_branch: schedule,
		});

		frappe.ui.form.on(`${doctype} Item`, {
			item_code: schedule,
			warehouse: schedule,
			uom: schedule,
			qty: schedule,
		});
	}
})();
