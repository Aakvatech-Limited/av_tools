const TARGET_DOCTYPE = "Purchase Receipt";
const PARTY_FIELD = "supplier";

const set_weighbridge_query = (frm) => {
  if (!frm.fields_dict.weighbridge_ticket) {
    return;
  }

  const query = () => ({
    filters: {
      target_document_type: ["in", ["", null, TARGET_DOCTYPE]],
      target_document_reference: ["in", ["", null]],
      document_type: ["!=", TARGET_DOCTYPE],
      docstatus: 1,
    },
  });

  frm.set_query("weighbridge_ticket", query);
  frm.fields_dict.weighbridge_ticket.get_query = query;
};

const set_fields_if_present = (frm, values) => {
  Object.entries(values || {}).forEach(([fieldname, value]) => {
    if (value === undefined || !frm.fields_dict[fieldname]) {
      return;
    }
    frm.set_value(fieldname, value);
  });
};

const get_ticket_route_options = (frm) => {
  const options = {
    document_type: frm.doctype,
    document_reference: frm.doc.name || undefined,
    company: frm.doc.company || undefined,
  };

  if (PARTY_FIELD === "customer") {
    options.customer = frm.doc.customer || undefined;
  } else {
    options.supplier = frm.doc.supplier || undefined;
  }

  return options;
};

const add_create_ticket_button = (frm) => {
  if (frm.doc.docstatus !== 1 || frm.doc.weighbridge_ticket) {
    return;
  }

  frm.add_custom_button(
    __("Weighbridge Ticket"),
    () => {
      frappe.new_doc("Weighbridge Ticket", get_ticket_route_options(frm));
    },
    __("Create")
  );
};

const apply_ticket_items = (frm, ticket) => {
  const items = ticket.items || [];
  if (!items.length) {
    frappe.msgprint(__("Selected Weighbridge Ticket has no items."));
    return;
  }

  frm.clear_table("items");
  items.forEach((row) => {
    const child = frm.add_child("items");
    child.item_code = row.item_code;
    if (row.item_name) {
      child.item_name = row.item_name;
    }
    if (row.qty != null) {
      child.qty = row.qty;
    }
    if (row.uom) {
      child.uom = row.uom;
    }
  });
  frm.refresh_field("items");
};

const apply_ticket_fields = (frm, ticket) => {
  const values = {
    company: ticket.company || undefined,
    posting_date: ticket.posting_date || undefined,
    transaction_date: ticket.posting_date || undefined,
    due_date: ticket.posting_date || undefined,
    set_posting_time: 1,
    posting_time: ticket.posting_time || undefined,
  };

  if (PARTY_FIELD === "customer") {
    values.customer = ticket.customer || undefined;
  } else {
    values.supplier = ticket.supplier || undefined;
  }

  set_fields_if_present(frm, values);
};

const handle_ticket_change = (frm, options = {}) => {
  if (!frm.doc.weighbridge_ticket) {
    return;
  }

  const { apply_values = true } = options;
  const documentName = frm.is_new() ? "" : frm.doc.name || "";

  frappe.call({
    method: "av_tools.weigh_bridge.api.get_ticket_items",
    args: {
      ticket: frm.doc.weighbridge_ticket,
      doctype: frm.doctype,
      document_name: documentName,
    },
    callback: (r) => {
      if (!r.message) {
        frappe.msgprint(__("Unable to load Weighbridge Ticket."));
        return;
      }

      if (!apply_values) {
        return;
      }

      apply_ticket_fields(frm, r.message);
      apply_ticket_items(frm, { items: r.message.items || [] });
    },
  });
};

frappe.ui.form.on(TARGET_DOCTYPE, {
  onload(frm) {
    set_weighbridge_query(frm);

    if (frm.doc.weighbridge_ticket && (!frm.doc.items || !frm.doc.items.length)) {
      handle_ticket_change(frm);
    }
  },
  refresh(frm) {
    set_weighbridge_query(frm);
    add_create_ticket_button(frm);
  },
  weighbridge_ticket(frm) {
    handle_ticket_change(frm);
  },
  after_save(frm) {
    if (frm.doc.weighbridge_ticket) {
      handle_ticket_change(frm, { apply_values: false });
    }
  },
});
