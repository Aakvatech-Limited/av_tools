// Copyright (c) 2026, Aakvatech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Implementation Handover Snapshot", {
	refresh(frm) {
		frm.remove_custom_button(__("Add All Sections"));
		frm.remove_custom_button(__("Generate Snapshot"));

		frm.add_custom_button(__("Add All Sections"), () => {
			frm.trigger("add_all_sections");
		});

		frm.add_custom_button(__("Generate Snapshot"), () => {
			frm.trigger("generate_snapshot");
		});
	},

	add_all_sections(frm) {
		return get_snapshot_section_options().then((sections) => {
			frm.clear_table("table_qvkt");

			sections.forEach((section) => {
				const row = frm.add_child("table_qvkt");
				row.reference = section;
			});

			frm.refresh_field("table_qvkt");
		});
	},

	generate_snapshot(frm) {
		return ensure_sections(frm)
			.then(() => frm.call("generate_snapshot"))
			.then((r) => {
				if (!r.message) {
					return;
				}

				frm.doc.name = r.message.name || frm.doc.name;
				frm.doc.__islocal = 0;
				frm.set_value("site_name", r.message.site_name);
				frm.set_value("generated_on", r.message.generated_on);
				frm.set_value("generated_by", r.message.generated_by);
				frm.clear_table("table_ldiu");

				(r.message.table_ldiu || []).forEach((snapshot_json) => {
					const row = frm.add_child("table_ldiu");
					row.type = snapshot_json.type;
					row.json_type = snapshot_json.json_type;
				});

				frm.refresh_field("table_ldiu");
				frm.doc.__unsaved = 0;
				frm.refresh_fields();
			});
	},
});

function ensure_sections(frm) {
	if ((frm.doc.table_qvkt || []).length) {
		return Promise.resolve();
	}

	return frm.trigger("add_all_sections");
}

function get_snapshot_section_options() {
	return frappe
		.call(
			"av_tools.av_tools.doctype.implementation_handover_snapshot.implementation_handover_snapshot.get_snapshot_section_options"
		)
		.then((r) => r.message || []);
}
