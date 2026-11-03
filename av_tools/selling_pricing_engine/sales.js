(() => {
  if (frappe.__selling_pricing_engine_loaded) return;
  frappe.__selling_pricing_engine_loaded = true;
  const api = "av_tools.selling_pricing_engine.sales";
  const configs = new Map();
  const configuration = (company) => {
    if (!company) return Promise.resolve({ enabled: false });
    if (!configs.has(company)) {
      configs.set(
        company,
        frappe.xcall(`${api}.sales_configuration`, { company })
      );
    }
    return configs.get(company);
  };
  async function refresh(frm) {
    if (
      frm.doc.docstatus !== 0 ||
      !(await configuration(frm.doc.company)).enabled
    )
      return;
    const request = (frm.__spe_request || 0) + 1;
    frm.__spe_request = request;
    const header = JSON.stringify([
      frm.doc.company,
      frm.doc.selling_price_list,
      frm.doc.currency,
      frm.doc.conversion_rate,
      frm.doc.plc_conversion_rate,
      frm.doc.transaction_date || frm.doc.posting_date,
      frm.doc.custom_spe_keep_manual_rates,
    ]);
    const rows = await frappe.xcall(`${api}.refresh_prices`, { doc: frm.doc });
    const current = JSON.stringify([
      frm.doc.company,
      frm.doc.selling_price_list,
      frm.doc.currency,
      frm.doc.conversion_rate,
      frm.doc.plc_conversion_rate,
      frm.doc.transaction_date || frm.doc.posting_date,
      frm.doc.custom_spe_keep_manual_rates,
    ]);
    if (request !== frm.__spe_request || current !== header) return;
    for (const result of rows) {
      const row = (frm.doc.items || []).find(
        (item) => item.name === result.name
      );
      if (
        !row ||
        row.item_code !== result.item_code ||
        row.warehouse !== result.warehouse ||
        row.uom !== result.uom
      )
        continue;
      await frappe.model.set_value(row.doctype, row.name, {
        price_list_rate: result.price_list_rate,
        rate: result.rate,
        custom_spe_price_source: result.custom_spe_price_source,
      });
    }
    await frm.trigger("calculate_taxes_and_totals");
  }
  const schedule = (frm) => frappe.after_ajax(() => refresh(frm));
  for (const doctype of ["Quotation", "Sales Order", "Sales Invoice"]) {
    frappe.ui.form.on(doctype, {
      async refresh(frm) {
        configs.delete(frm.doc.company);
        const config = await configuration(frm.doc.company);
        frm.toggle_display("custom_spe_keep_manual_rates", !!config.enabled);
        if (config.enabled && frm.doc.docstatus === 0) {
          frm.add_custom_button(__("Refresh Selling Prices"), () =>
            refresh(frm)
          );
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
    });
    frappe.ui.form.on(`${doctype} Item`, {
      warehouse: schedule,
      uom: schedule,
      qty: schedule,
    });
  }
})();
