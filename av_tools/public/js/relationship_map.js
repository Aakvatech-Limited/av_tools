/* Read-only SAP-style transaction map, shared across supported ERPNext forms. */
(() => {
    const supported = [
        "Material Request", "Request for Quotation", "Supplier Quotation",
        "Purchase Order", "Purchase Receipt", "Purchase Invoice",
        "Quotation", "Sales Order", "Delivery Note", "Sales Invoice",
        "Stock Entry", "Stock Reconciliation", "Payment Entry",
        "Payment Request", "Journal Entry",
    ];
    const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
    const label = (node) => ({
        0: "Draft", 1: "Submitted", 2: "Cancelled",
    })[node.docstatus] || "Unknown";
    const color = (node) => node.docstatus === 2 ? "red" : node.docstatus === 1 ? "green" : "orange";

    async function show_map(frm) {
        const dialog = new frappe.ui.Dialog({
            title: __("Relationship Map"),
            size: "extra-large",
            fields: [{ fieldtype: "HTML", fieldname: "map" }],
        });
        dialog.show();
        const target = dialog.fields_dict.map.$wrapper;
        target.html('<p class="text-muted">' + __("Loading linked documents...") + "</p>");
        try {
            const response = await frappe.call({
                method: "av_tools.relationship_map.get_relationship_map",
                args: { doctype: frm.doctype, name: frm.doc.name },
            });
            const graph = response.message;
            const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
            const parents = new Map();
            const children = new Map();
            graph.edges.forEach((edge) => {
                if (!parents.has(edge.target)) parents.set(edge.target, new Set());
                if (!children.has(edge.source)) children.set(edge.source, new Set());
                parents.get(edge.target).add(edge.source);
                children.get(edge.source).add(edge.target);
            });
            const card = (id) => {
                const node = nodes.get(id);
                if (!node) return "";
                const audit = node.authorization;
                const details = [
                    __("Created by") + ": " + (node.created_by || __("Unknown")),
                    __("Created at") + ": " + (node.created_at || __("Unknown")),
                    __("Submitted by") + ": " + (audit?.by || __("Not recorded")),
                    __("Submitted at") + ": " + (audit?.at || __("Not recorded")),
                    __("Last modified by") + ": " + (node.modified_by || __("Unknown")),
                    __("Last modified at") + ": " + (node.modified_at || __("Unknown")),
                ].join("\n");
                return `<div class="rm-card" data-type="${escape(node.doctype)}" data-name="${escape(node.name)}"
                    title="${escape(details)}" style="cursor:pointer;border:1px solid var(--border-color);
                    border-left:4px solid ${node.id === graph.root ? "var(--primary)" : "var(--border-color)"};
                    border-radius:8px;padding:10px;margin:7px 0;background:var(--card-bg);">
                    <div><b>${escape(node.doctype)}</b> · ${escape(node.name)}</div>
                    <small class="text-muted">${escape(label(node))} · ${escape(node.status || __("No status"))}</small>
                    <span class="indicator ${color(node)}" style="float:right"></span>
                </div>`;
            };
            // Each connected document is shown once within each section; no infinite cycles.
            const render_ids = (ids) => [...ids].sort().map(card).join("");
            const upstream = new Set(), downstream = new Set();
            const walk = (start, adjacency, result) => {
                const pending = [...(adjacency.get(start) || [])];
                while (pending.length) {
                    const id = pending.pop();
                    if (id === graph.root || result.has(id)) continue;
                    result.add(id);
                    for (const next of adjacency.get(id) || []) pending.push(next);
                }
            };
            walk(graph.root, parents, upstream);
            walk(graph.root, children, downstream);
            const included = new Set([...upstream, ...downstream, graph.root]);
            const additional = [...nodes.keys()].filter((id) => !included.has(id));
            target.html(`<div class="relationship-map" style="max-height:65vh;overflow:auto">
                <div class="text-muted small" style="margin-bottom:12px">${__("Click a document to open it. Hover to view audit information.")}</div>
                <h6>${__("Previous documents")}</h6>${render_ids(upstream) || '<p class="text-muted">' + __("None found") + "</p>"}
                <div style="text-align:center;padding:6px">↓</div>
                <h6>${__("Current document")}</h6>${card(graph.root)}
                <div style="text-align:center;padding:6px">↓</div>
                <h6>${__("Subsequent documents")}</h6>${render_ids(downstream) || '<p class="text-muted">' + __("None found") + "</p>"}
                ${additional.length ? '<h6>' + __("Other linked documents") + "</h6>" + render_ids(additional) : ""}
                ${graph.truncated ? '<p class="text-warning">' + __("Map limited to 60 documents.") + "</p>" : ""}
                </div>`);
            target.find(".rm-card").on("click", function () {
                frappe.set_route("Form", $(this).attr("data-type"), $(this).attr("data-name"));
                dialog.hide();
            });
        } catch (error) {
            target.text(__("Could not load relationship map. Check permissions and server logs."));
            console.error(error);
        }
    }
    supported.forEach((doctype) => {
        frappe.ui.form.on(doctype, {
            refresh(frm) {
                if (!frm.is_new()) {
                    frm.page.add_menu_item(__("Relationship Map"), () => show_map(frm), __("View"));
                }
            },
        });
    });
})();
