frappe.ui.form.on("Account", {
	onload_post_render: function (frm) {
		frm.trigger("parent_account");
		frm.trigger("create_expenses_item_btn");
		frm.set_query("item", function () {
			return {
				filters: {
					item_group: ["in", ["Indirect Expenses", "Indirect Income"]],
				},
			};
		});
	},
	refresh: function (frm) {
		frm.trigger("onload_post_render");
	},
	create_expenses_item_btn: function (frm) {
		frappe.db
			.get_single_value("AV Tools Settings", "enable_indirect_expense_item_creation")
			.then(function (enabled) {
				if (!enabled) return;
				frm.add_custom_button(__("Create Expense/Income Item"), function () {
					frappe.call({
						method: "av_tools.av_tools_hooks.account.add_indirect_expense_item",
						args: {
							account_name: frm.doc.name,
						},
						callback: function (r) {
							if (r.message) {
								frm.set_value("item", r.message);
								frm.refresh_field("item");
								frm.save();
							}
						},
					});
				});
			});
	},
	parent_account: function (frm) {
		frm.trigger("create_expenses_item_btn");
		frm.refresh_field("item");
	},
	item: function (frm) {
		frm.trigger("create_expenses_item_btn");
	},
});
