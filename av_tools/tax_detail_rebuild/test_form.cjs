// Exercise actual toolbar callbacks, including Frappe's document-call boundary.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function form(status, ready = 0, dirty = false) {
    const buttons = {};
    const events = [];
    const confirmations = [];
    let handlers;
    const frm = {
        doc: {doctype: "Item Wise Tax Detail Rebuild", name: "TEST-REBUILD", status, ready_count: ready},
        set_intro() {}, enable_save() {}, disable_save() {},
        dashboard: {set_headline_alert() {}},
        add_custom_button(label, callback) { buttons[label] = callback; },
        is_new() { return false; },
        is_dirty() { return dirty; },
        async save() { events.push("save"); dirty = false; },
        async call(options) {
            // Without doc, frm.call(object) dispatches to a module function.
            assert.strictEqual(options.doc, frm.doc, "RPC must carry the current document");
            assert.equal(options.freeze, true);
            assert.ok(["preview", "rebuild"].includes(options.method));
            events.push(options.method);
            return {};
        },
        async reload_doc() { events.push("reload"); }
    };
    const sandbox = {
        frappe: {
            ui: {form: {on(doctype, config) {
                assert.equal(doctype, "Item Wise Tax Detail Rebuild");
                handlers = config;
            }}},
            confirm(message, callback) {
                assert.ok(message.includes(String(ready)));
                confirmations.push(callback());
            }
        },
        clearTimeout() {}, setTimeout() { return 1; }, cur_frm: frm
    };
    const script = path.join(__dirname, "../av_tools/doctype/item_wise_tax_detail_rebuild/item_wise_tax_detail_rebuild.js");
    vm.runInNewContext(fs.readFileSync(script, "utf8"), sandbox, {filename: script});
    handlers.refresh(frm);
    return {frm, buttons, events, confirmations};
}

test("saved Draft Preview calls the document method and reloads", async () => {
    const state = form("Draft");
    await state.buttons.Preview();
    assert.deepEqual(state.events, ["preview", "reload"]);
});

test("dirty Draft saves before its document preview", async () => {
    const state = form("Draft", 0, true);
    await state.buttons.Preview();
    assert.deepEqual(state.events, ["save", "preview", "reload"]);
});

test("reviewed rebuild uses document RPC after confirmation", async () => {
    const state = form("Previewed", 3);
    state.buttons["Rebuild Ready Invoices"]();
    await Promise.all(state.confirmations);
    assert.deepEqual(state.events, ["rebuild", "reload"]);
});

test("a preview with no Ready invoices offers no rebuild action", () => {
    const state = form("Previewed", 0);
    assert.equal(state.buttons["Rebuild Ready Invoices"], undefined);
    assert.deepEqual(state.events, []);
});
