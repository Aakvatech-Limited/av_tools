/* SAP-inspired, read-only, dependency-free ERPNext relationship graph. */
(() => {
    const supported = [
        "Material Request", "Request for Quotation", "Supplier Quotation",
        "Purchase Order", "Purchase Receipt", "Purchase Invoice",
        "Quotation", "Sales Order", "Delivery Note", "Sales Invoice",
        "Stock Entry", "Stock Reconciliation", "Payment Entry",
        "Payment Request", "Journal Entry",
    ];
    const esc = (v) => frappe.utils.escape_html(String(v ?? ""));
    const state = (n) => ({ 0: __("Draft"), 1: __("Submitted"), 2: __("Cancelled") })[n.docstatus] || __("Unknown");
    const palette = (n, root) => n.docstatus === 2
        ? { border: "#c65b5b", header: "#f8dddd", marker: "#bf4444" }
        : n.docstatus === 0
            ? { border: "#cf9b33", header: "#fff1ba", marker: "#d49a22" }
            : { border: root ? "#3876b9" : "#87a4c3", header: root ? "#c7def6" : "#d9e7f4", marker: "#33835c" };
    const NODE_W = 210, NODE_H = 115, DX = 295, DY = 156, MARGIN = 46;
    const svgNS = "http://www.w3.org/2000/svg";

    function layout(graph, visibleNodes) {
        const byId = new Map(visibleNodes.map((n) => [n.id, n]));
        const edges = graph.edges.filter((e) => byId.has(e.source) && byId.has(e.target) && e.source !== e.target);
        const incoming = new Map(visibleNodes.map((n) => [n.id, []]));
        const outgoing = new Map(visibleNodes.map((n) => [n.id, []]));
        edges.forEach((e) => { incoming.get(e.target).push(e.source); outgoing.get(e.source).push(e.target); });
        // Bellman-Ford-like bounded relaxation; cycles are harmless and cannot loop forever.
        const dist = new Map(visibleNodes.map((n) => [n.id, 0]));
        const roots = visibleNodes.filter((n) => !incoming.get(n.id).length);
        const seed = roots.length ? roots : [byId.get(graph.root) || visibleNodes[0]];
        seed.forEach((n) => dist.set(n.id, 0));
        // Traverse breadth-first for rank, then relax forward along parent links.
        const queue = seed.map((n) => n.id), touched = new Set(queue);
        while (queue.length) {
            const id = queue.shift();
            for (const dest of outgoing.get(id)) {
                if (touched.has(dest)) continue;
                touched.add(dest);
                dist.set(dest, dist.get(id) + 1);
                queue.push(dest);
            }
        }
        visibleNodes.forEach((n) => { if (!touched.has(n.id)) dist.set(n.id, 0); });
        // Assign the current doc a stable position even when there are disconnected branches.
        const groups = new Map();
        visibleNodes.forEach((n) => {
            const rank = Math.min(visibleNodes.length, dist.get(n.id));
            if (!groups.has(rank)) groups.set(rank, []);
            groups.get(rank).push(n);
        });
        const ranks = [...groups.keys()].sort((a, b) => a - b);
        const positions = new Map();
        ranks.forEach((r, i) => {
            const nodes = groups.get(r);
            nodes.sort((a, b) => {
                const priority = (n) => {
                    const parents = incoming.get(n.id).map((p) => positions.get(p)?.y).filter((v) => v !== undefined);
                    return parents.length ? parents.reduce((x, y) => x + y, 0) / parents.length : 0;
                };
                return priority(a) - priority(b) || a.id.localeCompare(b.id);
            });
            nodes.forEach((n, row) => positions.set(n.id, { x: MARGIN + i * DX, y: MARGIN + row * DY }));
        });
        const rows = Math.max(1, ...[...groups.values()].map((v) => v.length));
        return { positions, edges, width: MARGIN * 2 + (ranks.length - 1) * DX + NODE_W,
            height: MARGIN * 2 + (rows - 1) * DY + NODE_H };
    }

    function draw(graph, nodes) {
        const { positions, edges, width, height } = layout(graph, nodes);
        const byId = new Map(nodes.map((n) => [n.id, n]));
        const arrows = edges.map((e) => {
            const a = positions.get(e.source), b = positions.get(e.target);
            const sx = a.x + NODE_W, sy = a.y + NODE_H / 2, tx = b.x, ty = b.y + NODE_H / 2;
            if (tx > sx) {
                const mid = (sx + tx) / 2;
                return `<path d="M ${sx} ${sy} C ${mid} ${sy}, ${mid} ${ty}, ${tx} ${ty}" fill="none" stroke="#83a9cf" stroke-width="2.7" marker-end="url(#rm-arrow)"/>`;
            }
            const midY = Math.max(sy, ty) + NODE_H / 2;
            return `<path d="M ${sx} ${sy} L ${sx + 16} ${sy} L ${sx + 16} ${midY} L ${tx - 15} ${midY} L ${tx - 15} ${ty} L ${tx} ${ty}" fill="none" stroke="#b1a8a0" stroke-width="1.7" stroke-dasharray="4 4" marker-end="url(#rm-arrow)"/>`;
        }).join("");
        const cards = nodes.map((n) => {
            const p = positions.get(n.id), colors = palette(n, n.id === graph.root);
            const details = [
                n.doctype + " " + n.name, __("State") + ": " + state(n),
                __("Business status") + ": " + (n.status || __("Not recorded")),
                __("Workflow state") + ": " + (n.workflow_state || __("Not recorded")),
                __("Amount") + ": " + (n.currency || "") + " " + (n.amount || __("Not recorded")),
                __("Created by") + ": " + (n.created_by || __("Unknown")),
                __("Created at") + ": " + (n.created_at || __("Unknown")),
                __("Authorized by") + ": " + (n.authorization?.by || __("Not recorded")),
                __("Authorized at") + ": " + (n.authorization?.at || __("Not recorded")),
                __("Modified by") + ": " + (n.modified_by || __("Unknown")),
                __("Modified at") + ": " + (n.modified_at || __("Unknown")),
            ].join("\n");
            const title = n.doctype.length > 25 ? n.doctype.slice(0, 23) + "…" : n.doctype;
            const number = n.name.length > 27 ? n.name.slice(0, 25) + "…" : n.name;
            return `<g class="rm-node" tabindex="0" role="link" data-id="${esc(n.id)}"
                transform="translate(${p.x},${p.y})" style="cursor:pointer">
                <title>${esc(details)}</title>
                <rect x="2" y="3" width="${NODE_W}" height="${NODE_H}" rx="3" fill="#b4b4b4" opacity=".22"/>
                <rect width="${NODE_W}" height="${NODE_H}" rx="3" fill="#fff" stroke="${colors.border}" stroke-width="${n.id === graph.root ? 2.5 : 1.3}"/>
                <path d="M 1 29 H ${NODE_W - 1}" stroke="${colors.border}" stroke-width="1"/>
                <path d="M 3 1 H ${NODE_W - 3} Q ${NODE_W - 1} 1 ${NODE_W - 1} 3 V 28 H 1 V 3 Q 1 1 3 1" fill="${colors.header}"/>
                <text x="${NODE_W / 2}" y="19" text-anchor="middle" font-size="13" font-weight="600" fill="#1b3045">${esc(title)}</text>
                <text x="${NODE_W - 9}" y="50" font-size="12" text-anchor="end" fill="#24364b">${esc(number)}</text>
                <text x="${NODE_W - 9}" y="69" font-size="11" text-anchor="end" fill="#566879">${esc(n.posting_date || n.transaction_date || (n.created_at || "").slice(0, 10))}</text>
                <text x="9" y="91" font-size="11" fill="#344054">${esc(state(n))}</text>
                <circle cx="${NODE_W - 15}" cy="86" r="5" fill="${colors.marker}"/>
                <text x="${NODE_W - 9}" y="106" font-size="10.5" text-anchor="end" fill="#536477">${esc((n.currency || "") + " " + (n.amount || (n.status || "").slice(0, 24)))}</text>
            </g>`;
        }).join("");
        return `<svg xmlns="${svgNS}" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img"
            aria-label="${esc(__("Document relationship map"))}" style="font-family:Arial,sans-serif;background:#fff">
            <defs><marker id="rm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 Z" fill="#83a9cf"/></marker></defs>${arrows}${cards}</svg>`;
    }

    async function show_map(frm) {
        const dialog = new frappe.ui.Dialog({
            title: __("Relationship Map"), size: "extra-large",
            fields: [{ fieldtype: "HTML", fieldname: "map" }],
        });
        dialog.show();
        const wrapper = dialog.fields_dict.map.$wrapper;
        wrapper.text(__("Loading linked documents..."));
        try {
            const result = await frappe.call({
                method: "av_tools.relationship_map.get_relationship_map",
                args: { doctype: frm.doctype, name: frm.doc.name },
            });
            const graph = result.message;
            if (!graph?.nodes?.length) throw new Error("Empty relationship graph");
            let scale = 1, showDraft = true, showCancelled = true;
            wrapper.html(`<div class="rm-controls" style="display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin-bottom:10px">
                <button class="btn btn-default btn-sm" data-action="in">+</button>
                <button class="btn btn-default btn-sm" data-action="out">−</button>
                <button class="btn btn-default btn-sm" data-action="fit">${__("Fit")}</button>
                <label style="margin:0 10px"><input type="checkbox" data-filter="draft" checked> ${__("Draft")}</label>
                <label style="margin:0 10px"><input type="checkbox" data-filter="cancelled" checked> ${__("Cancelled")}</label>
                <button class="btn btn-default btn-sm" data-action="svg">${__("Export SVG")}</button>
                <button class="btn btn-default btn-sm" data-action="png">${__("Export PNG")}</button>
                <button class="btn btn-default btn-sm" data-action="print">${__("Print")}</button></div>
                <div class="rm-viewport" style="height:60vh;min-height:350px;overflow:auto;border:1px solid var(--border-color);background:#fff;cursor:grab">
                <div class="rm-canvas" style="width:max-content;transform-origin:top left"></div></div>
                <div class="text-muted small" style="padding-top:7px">${__("Click a document to open it. Hover for authorization and audit details. Drag to pan.")}</div>
                ${graph.truncated ? '<div class="text-warning">' + __("Graph is truncated at the server traversal limit.") + "</div>" : ""}`);
            const viewport = wrapper.find(".rm-viewport");
            const canvas = wrapper.find(".rm-canvas");
            const render = () => {
                const nodes = graph.nodes.filter((n) => n.id === graph.root ||
                    (showDraft || n.docstatus !== 0) && (showCancelled || n.docstatus !== 2));
                canvas.html(draw(graph, nodes));
                const svg = canvas.find("svg");
                const w = Number(svg.attr("width")), h = Number(svg.attr("height"));
                canvas.css({ transform: "", width: w * scale, height: h * scale });
                svg.css({ width: w * scale, height: h * scale });
                svg.find(".rm-node").on("click keydown", function (event) {
                    if (event.type === "keydown" && event.key !== "Enter") return;
                    const id = $(this).attr("data-id");
                    const node = graph.nodes.find((n) => n.id === id);
                    if (!node) return;
                    frappe.set_route("Form", node.doctype, node.name);
                    dialog.hide();
                });
            };
            const fit = () => {
                const svg = canvas.find("svg");
                scale = Math.min(1.4, Math.max(.2, (viewport.width() - 20) / Number(svg.attr("width"))));
                render();
                viewport.scrollLeft(0).scrollTop(0);
            };
            const export_svg = () => {
                const svg = canvas.find("svg")[0];
                const raw = new XMLSerializer().serializeToString(svg);
                return new Blob([raw], { type: "image/svg+xml;charset=utf-8" });
            };
            const download = (blob, ext) => {
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "relationship-map-" + frm.doc.name + "." + ext;
                document.body.appendChild(a); a.click(); a.remove();
                setTimeout(() => URL.revokeObjectURL(url), 2000);
            };
            wrapper.find("[data-action]").on("click", async function () {
                const action = $(this).attr("data-action");
                if (action === "in" || action === "out") {
                    scale = Math.min(3, Math.max(.2, scale * (action === "in" ? 1.2 : 1 / 1.2))); render();
                } else if (action === "fit") fit();
                else if (action === "svg") download(export_svg(), "svg");
                else if (action === "png" || action === "print") {
                    const blob = export_svg(), url = URL.createObjectURL(blob);
                    const img = new Image();
                    img.onload = () => {
                        const drawing = canvas.find("svg");
                        const c = document.createElement("canvas");
                        c.width = Number(drawing.attr("width")) * 2;
                        c.height = Number(drawing.attr("height")) * 2;
                        const ctx = c.getContext("2d");
                        ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, c.width, c.height);
                        ctx.drawImage(img, 0, 0, c.width, c.height);
                        URL.revokeObjectURL(url);
                        if (action === "png") c.toBlob((b) => { if (b) download(b, "png"); }, "image/png");
                        else {
                            const win = window.open("", "_blank");
                            if (!win) { frappe.msgprint(__("Allow pop-ups to print the map.")); return; }
                            const photo = c.toDataURL("image/png");
                            win.document.write('<html><body style="margin:0"><img style="max-width:100%" src="' + photo + '"></body></html>');
                            win.document.close(); win.focus(); win.print();
                        }
                    };
                    img.onerror = () => URL.revokeObjectURL(url);
                    img.src = url;
                }
            });
            wrapper.find("[data-filter]").on("change", function () {
                if ($(this).attr("data-filter") === "draft") showDraft = this.checked;
                else showCancelled = this.checked;
                render();
            });
            let dragging = false, startX, startY, left, top;
            viewport.on("mousedown", (e) => {
                if ($(e.target).closest(".rm-node").length) return;
                dragging = true; startX = e.pageX; startY = e.pageY;
                left = viewport.scrollLeft(); top = viewport.scrollTop();
            });
            $(document).on("mouseup.relationship-map", () => { dragging = false; });
            viewport.on("mousemove", (e) => {
                if (dragging) viewport.scrollLeft(left - e.pageX + startX).scrollTop(top - e.pageY + startY);
            });
            dialog.$wrapper.on("hidden.bs.modal", () => $(document).off("mouseup.relationship-map"));
            render(); fit();
        } catch (err) {
            wrapper.text(__("Unable to load relationship map. Check the browser console and server logs."));
            console.error(err);
        }
    }
    supported.forEach((doctype) => frappe.ui.form.on(doctype, {
        refresh(frm) {
            if (!frm.is_new()) frm.page.add_menu_item(__("Relationship Map"), () => show_map(frm), __("View"));
        },
    }));
})();
