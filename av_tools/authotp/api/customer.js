// Copyright (c) 2023, Aakvatech and contributors
// For license information, please see license.txt

frappe.ui.form.on('Customer', {
    refresh: function (frm) {
        // Set query for default authotp method
        frm.set_query("default_authotp_method", function () {
            return {
                filters: {
                    "party_type": "Customer",
                    "party": frm.doc.name,
                    "docstatus": 1,
                }
            };
        });
    },
});

