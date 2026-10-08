// SQL Process administration has been retired: direct DB process control is unsafe.
frappe.ui.form.on("SQL Process", {
	refresh(frm) {
		frm.set_df_property("refresh_q", "hidden", 1);
		frm.set_df_property("process", "read_only", 1);
		frm.dashboard.set_headline(
			__(
				"Database process inspection and termination are disabled. Use your database administration tools."
			)
		);
	},
});
