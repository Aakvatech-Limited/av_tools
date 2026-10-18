frappe.ui.form.on("Asset Capitalization Reconciliation", {
  refresh(frm){
    frm.trigger("calculate_totals");
    frm.set_query("gl_entry", "sources", function(doc, cdt, cdn){
      const row = locals[cdt][cdn];
      if (row.source_voucher_type && row.source_voucher) {
        return {filters: {voucher_type: row.source_voucher_type, voucher_no: row.source_voucher}};
      }
      return {};
    });
  },
  calculate_totals(frm){
    let a=(frm.doc.assets||[]).reduce((v,r)=>v+flt(r.allocated_amount),0);
    let s=(frm.doc.sources||[]).reduce((v,r)=>v+flt(r.allocated_amount),0);
    frm.set_value("asset_total",a);frm.set_value("source_total",s);frm.set_value("variance",a-s);
  },
  validate(frm){
    let a=(frm.doc.assets||[]).reduce((v,r)=>v+flt(r.allocated_amount),0);
    let s=(frm.doc.sources||[]).reduce((v,r)=>v+flt(r.allocated_amount),0);
    frm.doc.asset_total=a;frm.doc.source_total=s;frm.doc.variance=a-s;
    if(frm.doc.status==="Approved"){
      if(!(frm.doc.assets||[]).length||!(frm.doc.sources||[]).length)frappe.throw("Both allocation tables are required.");
      if(Math.abs(a-s)>0.01)frappe.throw("Asset and source allocation totals must balance.");
      for(let r of frm.doc.assets||[])if(!r.asset||!flt(r.allocated_amount))frappe.throw("Asset rows need an Asset and non-zero amount.");
      for(let r of frm.doc.sources||[])if(!r.source_voucher_type||!r.source_voucher||!flt(r.allocated_amount))frappe.throw("Source rows need Voucher Type, Source Voucher and non-zero amount.");
    }
  }
});
frappe.ui.form.on("Asset Reconciliation Asset", {
  assets_remove(frm) { frm.trigger("calculate_totals"); },
  async asset(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const selected = row && row.asset;
    if (!selected) {
      await frappe.model.set_value(cdt, cdn, "allocated_amount", 0);
      frm.trigger("calculate_totals");
      return;
    }
    try {
      const response = await frappe.db.get_value(
        "Asset", selected, ["total_asset_cost", "company"]
      );
      const current = locals[cdt] && locals[cdt][cdn];
      if (!current || current.asset !== selected) return;
      const asset = response.message || {};
      if (frm.doc.company && asset.company && asset.company !== frm.doc.company) {
        frappe.msgprint("The selected Asset belongs to another company.");
        await frappe.model.set_value(cdt, cdn, "allocated_amount", 0);
        frm.trigger("calculate_totals");
        return;
      }
      await frappe.model.set_value(
        cdt, cdn, "allocated_amount", flt(asset.total_asset_cost)
      );
      frm.trigger("calculate_totals");
    } catch (error) {
      frappe.msgprint("Unable to retrieve the selected Asset cost.");
    }
  },
  allocated_amount(frm) { frm.trigger("calculate_totals"); }
});
frappe.ui.form.on("Asset Reconciliation Source", {
  sources_remove(frm) { frm.trigger("calculate_totals"); },
  source_voucher_type(frm, cdt, cdn) {
    frappe.model.set_value(cdt, cdn, "source_voucher", "");
    frappe.model.set_value(cdt, cdn, "gl_entry", "");
    frappe.model.set_value(cdt, cdn, "source_line", "");
    frappe.model.set_value(cdt, cdn, "allocated_amount", 0);
  },
  source_voucher(frm, cdt, cdn) {
    frappe.model.set_value(cdt, cdn, "gl_entry", "");
    frappe.model.set_value(cdt, cdn, "source_line", "");
    frappe.model.set_value(cdt, cdn, "allocated_amount", 0);
  },
  gl_entry(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.gl_entry) return;
    const selected = row.gl_entry;
    frappe.db.get_value("GL Entry", selected,
      ["voucher_type", "voucher_no", "company", "is_cancelled", "account", "debit", "credit"]
    ).then(res => {
      const d = res.message || {};
      const current = locals[cdt][cdn];
      if (!current || current.gl_entry !== selected) return;
      if (d.is_cancelled || (frm.doc.company && d.company !== frm.doc.company)) {
        frappe.msgprint("GL Entry is cancelled or belongs to a different company.");
        frappe.model.set_value(cdt, cdn, "allocated_amount", 0);
        return;
      }
      if (d.voucher_type !== current.source_voucher_type ||
          d.voucher_no !== current.source_voucher) {
        frappe.msgprint("GL Entry does not belong to the selected voucher.");
        frappe.model.set_value(cdt, cdn, "allocated_amount", 0);
        return;
      }
      frappe.model.set_value(cdt, cdn, "allocated_amount",
        flt(d.debit) - flt(d.credit));
      frm.trigger("calculate_totals");
    });
  },
  select_source_line(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.source_voucher_type || !row.source_voucher) {
      frappe.msgprint("Select Voucher Type and Source Voucher first.");
      return;
    }
    const type = row.source_voucher_type;
    const name = row.source_voucher;
    if (!["Purchase Invoice", "Journal Entry", "Purchase Receipt"].includes(type)) {
      frappe.msgprint("Line selection is available for Purchase Invoice, Journal Entry and Purchase Receipt.");
      return;
    }
    frappe.db.get_doc(type, name).then(doc => {
      const current = locals[cdt] && locals[cdt][cdn];
      if (!current || current.source_voucher_type !== type || current.source_voucher !== name) return;
      if (frm.doc.company && doc.company !== frm.doc.company) {
        frappe.msgprint("Voucher belongs to another company.");
        return;
      }
      if (doc.docstatus !== 1) {
        frappe.msgprint("Only submitted vouchers may be allocated.");
        return;
      }
      const lines = type === "Journal Entry" ? (doc.accounts || []) : (doc.items || []);
      if (!lines.length) {
        frappe.msgprint("No source lines found.");
        return;
      }
      const options = lines.map((line, index) => {
        const amount = type === "Journal Entry"
          ? flt(line.debit) - flt(line.credit)
          : flt(line.base_net_amount != null ? line.base_net_amount : line.base_amount);
        const caption = type === "Journal Entry"
          ? (line.account || "Account")
          : (line.item_name || line.item_code || "Item");
        return {label: (index + 1) + ". " + caption + " | " + format_currency(amount, doc.currency || undefined) + " | " + line.name,
          value: String(index)};
      });
      const dialog = new frappe.ui.Dialog({
        title: "Select source line from " + name,
        fields: [{fieldname:"line_index",fieldtype:"Select",label:"Source line",reqd:1,
          options:options.map(x=>x.value + ": " + x.label).join("\n")}],
        primary_action_label:"Select line",
        primary_action(values) {
          const current = locals[cdt] && locals[cdt][cdn];
          if (!current || current.source_voucher_type !== type || current.source_voucher !== name) {
            dialog.hide();
            return;
          }
          const index = Number((values.line_index || "").split(":")[0]);
          const line = lines[index];
          if (!line) return;
          const amount = type === "Journal Entry"
            ? flt(line.debit) - flt(line.credit)
            : flt(line.base_net_amount != null ? line.base_net_amount : line.base_amount);
          frappe.model.set_value(cdt, cdn, "source_line", line.name);
          frappe.model.set_value(cdt, cdn, "allocated_amount", amount);
          frm.trigger("calculate_totals");
          dialog.hide();
        }
      });
      dialog.show();
    }).catch(() => frappe.msgprint("Unable to load source voucher lines."));
  },
  allocated_amount(frm) { frm.trigger("calculate_totals"); }
});
