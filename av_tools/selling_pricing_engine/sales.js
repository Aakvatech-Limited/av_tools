// This file is loaded via doctype_js and concatenated into meta.__js after
// other scripts that may not end with a semicolon. It must NOT start with
// "(", "[" or a template literal, otherwise it is parsed as a call on the
// previous script's last expression ("frappe.ui.form.on(...) is not a function").
// The namespace below is the first statement and also holds the module state.
frappe.provide("av_tools.selling_pricing_engine");

(() => {
	const spe = av_tools.selling_pricing_engine;
	if (spe.loaded) return;
	spe.loaded = true;

	const API = "av_tools.selling_pricing_engine.sales";
	const DOCTYPES = ["Quotation", "Sales Order", "Sales Invoice"];
	spe.configs = new Map();

	// Cache the promise (not the value) so simultaneous triggers share one request.
	// On failure, drop the cache entry so a transient error is retried next time.
	const getConfiguration = (company) => {
		if (!company) return Promise.resolve({ enabled: false });
		if (!spe.configs.has(company)) {
			const request = frappe
				.xcall(`${API}.sales_configuration`, { company })
				.then((config) => config || { enabled: false })
				.catch((error) => {
					console.warn("SPE: failed to load pricing configuration", error);
					spe.configs.delete(company);
					return { enabled: false };
				});
			spe.configs.set(company, request);
		}
		return spe.configs.get(company);
	};

	const headerSnapshot = (doc) =>
		JSON.stringify([
			doc.company,
			doc.selling_price_list,
			doc.currency,
			doc.conversion_rate,
			doc.plc_conversion_rate,
			doc.transaction_date || doc.posting_date,
			doc.custom_spe_keep_manual_rates,
			doc.custom_spe_branch,
		]);

	const isDraft = (frm) => !!frm && !!frm.doc && frm.doc.docstatus === 0;

	async function refresh(frm) {
		if (!isDraft(frm)) return;

		const config = await getConfiguration(frm.doc.company);
		if (!config.enabled) return;

		const request = (frm.__spe_request || 0) + 1;
		frm.__spe_request = request;
		const header = headerSnapshot(frm.doc);

		let rows;
		try {
			rows = await frappe.xcall(`${API}.refresh_prices`, { doc: frm.doc });
		} catch (error) {
			// Server messages (frappe.throw) are already shown by the request handler.
			console.warn("SPE: price refresh failed", error);
			return;
		}

		// Discard stale responses if the user changed the header or triggered another refresh.
		if (request !== frm.__spe_request || headerSnapshot(frm.doc) !== header) return;
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
		if (isDraft(frm)) frappe.after_ajax(() => refresh(frm));
	};

	const toggle = (frm, fieldname, show) => {
		if (frm.fields_dict[fieldname]) frm.toggle_display(fieldname, show);
	};

	for (const doctype of DOCTYPES) {
		frappe.ui.form.on(doctype, {
			async refresh(frm) {
				if (!frm.doc.company) return;

				spe.configs.delete(frm.doc.company);
				const config = await getConfiguration(frm.doc.company);

				toggle(frm, "custom_spe_keep_manual_rates", !!config.enabled);
				toggle(frm, "custom_spe_branch", !!config.expanded);

				if (config.enabled && isDraft(frm)) {
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
