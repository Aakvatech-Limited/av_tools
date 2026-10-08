frappe.ui.form.on("Bank Transaction Backfill", {
  refresh(frm) {
    if (frm.doc.docstatus !== 0) return;
    frm.add_custom_button(__("Preview Eligible Transactions"), async () => {
      if (!frm.doc.company || !frm.doc.source_doctype || !frm.doc.from_date || !frm.doc.to_date) {
        frappe.msgprint(__("Choose Company, Source DocType and clearance date range first."));
        return;
      }
      if (frm.is_dirty()) await frm.save();
      const response = await frappe.call({
        method: "av_tools.av_tools.doctype.bank_transaction_backfill.bank_transaction_backfill.preview_candidates",
        args: { name: frm.doc.name },
        freeze: true
      });
      frm.clear_table("entries");
      for (const row of response.message || []) frm.add_child("entries", row);
      frm.refresh_field("entries");
      await frm.save();
      frappe.show_alert({ message: __("{0} eligible candidate(s) saved for review.", [(response.message || []).length]), indicator: "blue" });
    });
  }
});