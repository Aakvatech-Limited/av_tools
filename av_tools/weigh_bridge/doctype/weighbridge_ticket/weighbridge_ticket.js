// Copyright (c) 2026, Aakvatech and contributors
// For license information, please see license.txt

const DEFAULT_UOM = "Kg";
const CREATE_TARGET_DOCTYPES = [
  "Sales Invoice",
  "Delivery Note",
  "Sales Order",
  "Purchase Order",
  "Purchase Invoice",
  "Purchase Receipt",
];
const CREATE_TARGETS_BY_SOURCE = {
  "Sales Order": ["Sales Invoice"],
  "Delivery Note": ["Sales Invoice"],
  "Purchase Order": ["Purchase Invoice"],
  "Purchase Receipt": ["Purchase Invoice"],
  "Sales Invoice": [],
  "Purchase Invoice": [],
};
const SALES_DOCTYPES = ["Sales Invoice", "Delivery Note", "Sales Order"];
const PURCHASE_DOCTYPES = ["Purchase Order", "Purchase Invoice", "Purchase Receipt"];

const distribute_net_weight = (frm, netWeight) => {
  const items = frm.doc.items || [];
  if (!items.length) {
    return;
  }

  const totalQty = items.reduce((sum, row) => sum + flt(row.qty || 0), 0);
  const useProportional = totalQty > 0;
  const perItem = items.length ? flt(netWeight) / items.length : 0;

  items.forEach((row) => {
    const qty = useProportional
      ? (flt(row.qty || 0) / totalQty) * flt(netWeight)
      : perItem;
    frappe.model.set_value(row.doctype, row.name, "qty", qty);
    frappe.model.set_value(row.doctype, row.name, "uom", DEFAULT_UOM);
  });
};

const set_net_weight = (frm) => {
  if (frm.doc.tare_weight != null && frm.doc.gross_weight != null) {
    const net = flt(frm.doc.gross_weight) - flt(frm.doc.tare_weight);
    frm.set_value("net_weight", net);
    distribute_net_weight(frm, net);
  }
};

const save_after_weight_capture = (frm) => {
  if (!frm.is_dirty() || frm._weight_save_in_progress) {
    return Promise.resolve();
  }

  frm._weight_save_in_progress = true;
  const save_result = frm.save();
  if (save_result && typeof save_result.finally === "function") {
    return save_result.finally(() => {
      frm._weight_save_in_progress = false;
    });
  }
  frm._weight_save_in_progress = false;
  return Promise.resolve();
};

const set_document_reference_query = (frm) => {
  frm.set_query("document_reference", () => ({
    filters: {
      docstatus: ["!=", 2],
      weighbridge_ticket: ["in", ["", null]],
    },
  }));
};

const get_create_route_options = (frm, targetDoctype) => {
  const options = {
    weighbridge_ticket: frm.doc.name,
    company: frm.doc.company || undefined,
    posting_date: frm.doc.posting_date || undefined,
    transaction_date: frm.doc.posting_date || undefined,
    due_date: frm.doc.posting_date || undefined,
    set_posting_time: 1,
    posting_time: frm.doc.posting_time || undefined,
  };

  if (SALES_DOCTYPES.includes(targetDoctype)) {
    options.customer = frm.doc.customer || undefined;
  }

  if (PURCHASE_DOCTYPES.includes(targetDoctype)) {
    options.supplier = frm.doc.supplier || undefined;
  }

  return options;
};

const add_create_buttons = (frm) => {
  if (frm.doc.docstatus !== 1) {
    return;
  }

  if (frm.doc.target_document_reference) {
    return;
  }

  const targets =
    CREATE_TARGETS_BY_SOURCE[frm.doc.document_type] || CREATE_TARGET_DOCTYPES;

  targets.forEach((targetDoctype) => {
    frm.add_custom_button(
      __(targetDoctype),
      () => {
        frappe.new_doc(targetDoctype, get_create_route_options(frm, targetDoctype));
      },
      __("Create")
    );
  });
};

const apply_reference_items = (frm, items) => {
  frm.clear_table("items");
  (items || []).forEach((row) => {
    if (!row.item_code) {
      return;
    }
    const child = frm.add_child("items");
    child.item_code = row.item_code;
    if (row.item_name) {
      child.item_name = row.item_name;
    }
    if (row.qty != null) {
      child.qty = flt(row.qty);
    }
    if (row.uom) {
      child.uom = row.uom;
    }
  });
  frm.refresh_field("items");
  toggle_read_buttons(frm);
};

const apply_reference_party = (frm, referenceData) => {
  const data = referenceData || {};
  const isSalesDoc = ["Sales Invoice", "Delivery Note", "Sales Order"].includes(
    frm.doc.document_type
  );
  const isPurchaseDoc = [
    "Purchase Order",
    "Purchase Invoice",
    "Purchase Receipt",
  ].includes(frm.doc.document_type);

  const values = {
    company: data.company || null,
    customer: isSalesDoc ? data.customer || null : null,
    supplier: isPurchaseDoc ? data.supplier || null : null,
  };

  return frm.set_value(values);
};

const load_reference_items = (frm) => {
  if (!frm.doc.document_type || !frm.doc.document_reference) {
    return;
  }

  frappe.call({
    method: "av_tools.weigh_bridge.api.get_reference_items",
    args: {
      document_type: frm.doc.document_type,
      document_reference: frm.doc.document_reference,
    },
    callback: (r) => {
      if (!r.message) {
        frappe.msgprint(__("Unable to load items from reference document."));
        return;
      }
      apply_reference_party(frm, r.message);
      apply_reference_items(frm, r.message.items || []);
    },
  });
};

const auto_load_reference_items = (frm) => {
  if (!frm.is_new()) {
    return;
  }
  if (frm._auto_reference_loaded) {
    return;
  }
  if (!frm.doc.document_type || !frm.doc.document_reference) {
    return;
  }
  if ((frm.doc.items || []).length) {
    return;
  }

  frm._auto_reference_loaded = true;
  load_reference_items(frm);
};

const ensure_gateway_payload = (frm, callback) => {
  // Always refresh from settings in case URL was updated while form is open.
  frappe.call({
    method: "av_tools.weigh_bridge.api.get_gateway_payload",
    callback: (r) => {
      if (!r.message) {
        frappe.msgprint(__("Weighbridge Settings are not configured."));
        return;
      }
      frm._read_weight_url = (r.message.read_weight_url || "").replace(/\/+$/, "");
      callback();
    },
  });
};

const parse_valpoids = (xmlText) => {
  const match = xmlText.match(
    /<id>ValPoids<\/id><value>\s*([^<]+)<\/value>/i
  );
  if (!match) {
    throw new Error("ValPoids not found in response.");
  }
  const rawValue = match[1].trim();
  const numberMatch = rawValue.match(/[-+]?\d*\.?\d+/);
  if (!numberMatch) {
    throw new Error("No numeric weight found in response.");
  }
  return {
    weight: flt(numberMatch[0]),
    raw: rawValue,
  };
};

const parse_weight_from_raw_text = (text) => {
  const rawText = (text || "").trim();
  if (!rawText) {
    return null;
  }

  let data;
  try {
    data = JSON.parse(rawText);
  } catch (err) {
    data = null;
  }

  if (data) {
    const directWeight =
      data.weight ??
      data.Weight ??
      data.value ??
      data.Value ??
      (data.data && data.data.weight);

    if (directWeight != null) {
      return {
        weight: flt(directWeight),
        raw: data.raw || String(directWeight),
      };
    }

    if (typeof data.raw === "string") {
      const m = data.raw.match(/[-+]?\d*\.?\d+/);
      if (m) {
        return {
          weight: flt(m[0]),
          raw: data.raw,
        };
      }
    }
  }

  try {
    return parse_valpoids(rawText);
  } catch (err) {
    const m = rawText.match(/[-+]?\d*\.?\d+/);
    if (m) {
      return {
        weight: flt(m[0]),
        raw: rawText,
      };
    }
    return null;
  }
};

const read_weight_client = (frm, target_field, time_field) => {
  const items = frm.doc.items || [];
  if (!items.length) {
    frappe.msgprint(__("Please add at least one item before reading weight."));
    return;
  }

  ensure_gateway_payload(frm, () => {
    if (!frm._read_weight_url) {
      frappe.msgprint(__("Read Weight URL is not configured."));
      return;
    }

    const call_url = (url) =>
      fetch(url, { method: "GET", cache: "no-store" }).then((response) =>
        response.text().then((text) => ({
          ok: response.ok,
          status: response.status,
          contentType: response.headers.get("content-type"),
          text,
          url,
        }))
      );

    call_url(frm._read_weight_url)
      .then((response) =>
        !response.ok
          ? response
          : (() => {
              const parsed = parse_weight_from_raw_text(response.text || "");
              if (parsed || /\/read_weight$/i.test(response.url)) {
                return response;
              }
              const retry_url = `${response.url.replace(/\/+$/, "")}/read_weight`;
              return call_url(retry_url);
            })()
      )
      .then((result) => {
        if (!result.ok) {
          frappe.msgprint(result.text || `HTTP ${result.status}`);
          return;
        }

        const data = parse_weight_from_raw_text(result.text || "");

        if (!data || data.weight == null) {
          frappe.msgprint(
            __(
              "Missing weight in response from {0} (HTTP {1}).",
              [result.url, result.status]
            )
          );
          // eslint-disable-next-line no-console
          console.error("Weighbridge raw response", result);
          return;
        }

        Promise.resolve(frm.set_value(target_field, data.weight))
          .then(() => frm.set_value(time_field, frappe.datetime.now_datetime()))
          .then(() => {
            set_net_weight(frm);
            return save_after_weight_capture(frm);
          })
          .then(() => {
            const label =
              target_field === "tare_weight"
                ? __("Tare Weight")
                : __("Gross Weight");
            frappe.show_alert(
              {
                message: __("{0} captured: {1}", [label, format_number(data.weight)]),
                indicator: "green",
              },
              5
            );
          });
      })
      .catch((error) => {
        frappe.msgprint(error.message);
        // eslint-disable-next-line no-console
        console.error(error);
      });
  });
};

const toggle_read_buttons = (frm) => {
  const hasItems = (frm.doc.items || []).length > 0;
  frm.set_df_property("read_tare", "read_only", !hasItems);
  frm.set_df_property("read_gross", "read_only", !hasItems);
};

frappe.ui.form.on("Weighbridge Ticket", {
  refresh(frm) {
    set_document_reference_query(frm);
    toggle_read_buttons(frm);
    add_create_buttons(frm);
    auto_load_reference_items(frm);
  },
  document_type(frm) {
    frm._auto_reference_loaded = false;
    frm.set_value("document_reference", null);
    apply_reference_party(frm, {});
    apply_reference_items(frm, []);
  },
  document_reference(frm) {
    if (!frm.doc.document_reference) {
      frm._auto_reference_loaded = false;
      apply_reference_party(frm, {});
      apply_reference_items(frm, []);
      return;
    }
    frm._auto_reference_loaded = true;
    load_reference_items(frm);
  },
  items_add(frm) {
    toggle_read_buttons(frm);
  },
  items_remove(frm) {
    toggle_read_buttons(frm);
  },
  items_on_form_rendered(frm) {
    toggle_read_buttons(frm);
  },
  read_tare(frm) {
    read_weight_client(frm, "tare_weight", "tare_time");
  },
  read_gross(frm) {
    read_weight_client(frm, "gross_weight", "gross_time");
  },
  tare_weight(frm) {
    set_net_weight(frm);
  },
  gross_weight(frm) {
    set_net_weight(frm);
  },
});
