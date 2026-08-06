/* global ctrlQ */

// Material Request ctrl+q shortcut (moved from csf_tz)

frappe.require(["/assets/av_tools/js/shortcuts.js"]);

frappe.ui.keys.add_shortcut({
	shortcut: "ctrl+q",
	action: () => {
		ctrlQ("Material Request Item", window.cur_page?.page?.frm);
	},
	page: this.page,
	description: __("Select Item Warehouse"),
	ignore_inputs: true,
});
