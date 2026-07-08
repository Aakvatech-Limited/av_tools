// Registered immediately — no app_ready dependency needed for jQuery events.
// Frappe triggers 'form-refresh' on every form load/reload with the frm instance.
$(document).on('form-refresh', function (e, frm) {
    setTimeout(function () { setup_approver_buttons(frm); }, 50);
});

$(document).on('app_ready', function () {
    var doctypes = (frappe.boot && frappe.boot.parallel_approval_doctypes) || [];

    // Register frappe.ui.form.on handlers when boot data is available.
    // This path fires in step 4 of frappe.run_serially (before setTimeout).
    if (doctypes.length) {
        doctypes.forEach(function (doctype) {
            frappe.ui.form.on(doctype, {
                refresh: function (frm) { setup_approver_buttons(frm); }
            });
        });
    }

    // Fallback: 500ms after route change guarantees cur_frm is fully loaded.
    frappe.router.on('change', function () {
        setTimeout(function () {
            if (cur_frm && cur_frm.doc) { setup_approver_buttons(cur_frm); }
        }, 500);
    });
});

function setup_approver_buttons(frm) {
    if (!frm || !frm.doc) return;

    var rows = frm.doc.custom_av_approver_details;
    if (!rows || !rows.length) return;

    // Prevent duplicate buttons when multiple paths fire on the same refresh.
    if (frm.custom_buttons && (frm.custom_buttons[__('Mark as Approved')] ||
        frm.custom_buttons[__('Reject')] ||
        frm.custom_buttons[__('Clear Rejection')])) {
        return;
    }

    var current_user = frappe.session.user;
    var approver_row = null;

    for (var i = 0; i < rows.length; i++) {
        if (rows[i].approver === current_user || rows[i].delegate_to === current_user) {
            approver_row = rows[i];
            break;
        }
    }
    if (!approver_row) return;

    var is_expired = approver_row.expiry_date && frappe.datetime.get_diff(frappe.datetime.now_date(), approver_row.expiry_date) > 0;
    if (is_expired && current_user === approver_row.approver) {
        if (approver_row.delegate_to) {
            frappe.show_alert({
                message: __('Your approval authority for this document expired on {0}. This has been escalated to {1}.', [frappe.datetime.str_to_user(approver_row.expiry_date), approver_row.delegate_to]),
                indicator: 'orange'
            });
            return;
        }
        frappe.show_alert({
            message: __('Your approval authority for this document expired on {0}, but no delegate is set, so you may still act.', [frappe.datetime.str_to_user(approver_row.expiry_date)]),
            indicator: 'orange'
        });
    }

    var group = __('Approval');

    if (!approver_row.approved && !approver_row.rejected) {
        frm.add_custom_button(__('Mark as Approved'), function () {
            frappe.call({
                method: 'av_tools.av_tools_hooks.parallel_approval.submit_approval_action',
                args: { doctype: frm.doc.doctype, docname: frm.doc.name, action: 'approve' },
                freeze: true,
                freeze_message: __('Submitting approval…'),
                callback: function (r) {
                    if (!r.exc) {
                        frappe.show_alert({ message: __('Approved successfully'), indicator: 'green' });
                        frm.reload_doc();
                    }
                }
            });
        }, group);

        frm.add_custom_button(__('Reject'), function () {
            var d = new frappe.ui.Dialog({
                title: __('Rejection Reason'),
                fields: [{ fieldname: 'reason', label: __('Reason'), fieldtype: 'Small Text', reqd: 1 }],
                primary_action_label: __('Confirm Rejection'),
                primary_action: function () {
                    var reason = d.get_value('reason');
                    if (!reason) { frappe.msgprint(__('Please enter a rejection reason.')); return; }
                    frappe.call({
                        method: 'av_tools.av_tools_hooks.parallel_approval.submit_approval_action',
                        args: { doctype: frm.doc.doctype, docname: frm.doc.name, action: 'reject', reason: reason },
                        freeze: true,
                        freeze_message: __('Submitting rejection…'),
                        callback: function (r) {
                            if (!r.exc) {
                                d.hide();
                                frappe.show_alert({ message: __('Document rejected'), indicator: 'red' });
                                frm.reload_doc();
                            }
                        }
                    });
                }
            });
            d.show();
        }, group);
    }

    if (approver_row.rejected) {
        frm.add_custom_button(__('Clear Rejection'), function () {
            frappe.call({
                method: 'av_tools.av_tools_hooks.parallel_approval.submit_approval_action',
                args: { doctype: frm.doc.doctype, docname: frm.doc.name, action: 'clear_rejection' },
                freeze: true,
                callback: function (r) {
                    if (!r.exc) {
                        frappe.show_alert({ message: __('Rejection cleared'), indicator: 'green' });
                        frm.reload_doc();
                    }
                }
            });
        }, group);
    }
}
