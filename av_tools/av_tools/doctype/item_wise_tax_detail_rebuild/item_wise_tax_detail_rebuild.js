frappe.ui.form.on("Item Wise Tax Detail Rebuild", {
    setup(frm) {
        frm.set_query("source_invoice", () => ({filters: {company: frm.doc.company, docstatus: 1}}));
    },
    source_doctype(frm) { frm.set_value("source_invoice", ""); },
    company(frm) { frm.set_value("source_invoice", ""); },
    refresh(frm) {
        if (frm.tax_rebuild_timer) clearTimeout(frm.tax_rebuild_timer);
        frm.set_intro("Rebuild derived item-wise details from saved transaction rates. Percentage-on-net taxes only; invoice-level discounts and other charge types are blocked. Preview before applying.", "blue");
        if (frm.doc.status === "Draft") {
            frm.enable_save();
            frm.add_custom_button("Preview", async () => {
                if (frm.is_new() || frm.is_dirty()) await frm.save();
                await frm.call({method: "preview", doc: frm.doc, freeze: true, freeze_message: "Checking saved rates and posted tax totals..."});
                await frm.reload_doc();
            });
        } else {
            frm.disable_save();
        }
        if (frm.doc.status === "Previewed" && frm.doc.ready_count) {
            frm.add_custom_button("Rebuild Ready Invoices", () => {
                frappe.confirm(`Replace the derived item-wise tax details for ${frm.doc.ready_count} previewed invoices? Invoice financial fields and GL entries will not be recalculated.`, async () => {
                    await frm.call({method: "rebuild", doc: frm.doc, freeze: true, freeze_message: "Queuing rebuild..."});
                    await frm.reload_doc();
                });
            });
        }
        if (!frm.is_new()) {
            frm.dashboard.set_headline_alert(`${frm.doc.status} | Scanned: ${frm.doc.scanned_count || 0} | Ready: ${frm.doc.ready_count || 0} | Blocked: ${frm.doc.blocked_count || 0} | Rebuilt: ${frm.doc.rebuilt_count || 0} | Failed: ${frm.doc.failed_count || 0}`);
        }
        if (["Queued", "Running"].includes(frm.doc.status)) {
            frm.tax_rebuild_timer = setTimeout(() => {
                if (cur_frm === frm && !frm.is_dirty()) frm.reload_doc();
            }, 3000);
        }
    }
});
