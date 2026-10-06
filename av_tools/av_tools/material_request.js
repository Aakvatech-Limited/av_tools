// Material Request ctrl+q shortcut (moved from csf_tz)

frappe.require(["/assets/av_tools/js/shortcuts.js"]);

frappe.ui.keys.add_shortcut({
	shortcut: "ctrl+q",
	action: () => {
		ctrlQ("Material Request Item");
	},
	page: this.page,
	description: __("Select Item Warehouse"),
	ignore_inputs: true,
});

frappe.ui.form.on("Material Request", {
	async after_save(frm) {
		const require_review = await frappe.db.get_single_value(
			"AV Tools Settings",
			"require_material_request_review"
		);

		if (!require_review) {
			return;
		}

		const allowed_types = ["Material Issue", "Material Transfer"];

		if (!allowed_types.includes(frm.doc.material_request_type)) {
			return;
		}

		if (!frm.doc.items || !frm.doc.items.length) {
			return;
		}

		await show_material_request_review(frm);
	},
});

async function show_material_request_review(frm) {
	const results = [];

	for (const row of frm.doc.items) {
		const target_warehouse = row.warehouse;

		if (!row.item_code || !target_warehouse) {
			continue;
		}

		let last_request_date = null;
		let last_request_qty = null;
		let last_material_request = null;

		const previous_requests = await frappe.db.get_list("Material Request", {
			filters: [
				["Material Request", "docstatus", "=", 1],
				[
					"Material Request",
					"material_request_type",
					"in",
					["Material Issue", "Material Transfer"],
				],
				["Material Request", "name", "!=", frm.doc.name],
				["Material Request Item", "item_code", "=", row.item_code],
				["Material Request Item", "warehouse", "=", target_warehouse],
			],
			fields: ["name", "transaction_date", "creation"],
			order_by: "transaction_date desc, creation desc",
			limit: 1,
		});

		if (previous_requests && previous_requests.length) {
			const previous_parent = previous_requests[0];

			last_material_request = previous_parent.name;
			last_request_date = previous_parent.transaction_date;

			const previous_doc = await frappe.db.get_doc(
				"Material Request",
				previous_parent.name
			);

			if (previous_doc && previous_doc.items && previous_doc.items.length) {
				const matching_row = previous_doc.items.find(
					item =>
						item.item_code === row.item_code &&
						item.warehouse === target_warehouse
				);

				if (matching_row) {
					last_request_qty = matching_row.qty;
				}
			}
		}

		let current_stock = 0;

		try {
			const bin_result = await frappe.db.get_value(
				"Bin",
				{
					item_code: row.item_code,
					warehouse: target_warehouse,
				},
				"actual_qty"
			);

			if (
				bin_result &&
				bin_result.message &&
				bin_result.message.actual_qty !== undefined &&
				bin_result.message.actual_qty !== null
			) {
				current_stock = bin_result.message.actual_qty;
			}
		} catch (error) {
			current_stock = null;
		}

		results.push({
			item_code: row.item_code,
			item_name: row.item_name || row.item_code,
			target_warehouse,
			last_material_request,
			last_request_date,
			last_request_qty,
			current_stock,
			current_requested_qty: row.qty || 0,
		});
	}

	if (!results.length) {
		return;
	}

	show_review_dialog(results);
}

function show_review_dialog(results) {
	let html = `
		<div style="margin-bottom:15px;">
			<b>
				${__(
					"Please review the previous request and current stock at the target warehouse."
				)}
			</b>
		</div>

		<div class="table-responsive">
			<table class="table table-bordered table-hover">
				<thead>
					<tr>
						<th>${__("Item")}</th>
						<th>${__("Target Warehouse")}</th>
						<th>${__("Last Requested Date")}</th>
						<th class="text-right">${__("Last Requested Qty")}</th>
						<th class="text-right">${__("Current Stock")}</th>
						<th class="text-right">${__("Current Requested Qty")}</th>
					</tr>
				</thead>
				<tbody>
	`;

	results.forEach(row => {
		let item_html = `
			<b>${escape_html(row.item_code)}</b>
		`;

		if (row.item_name && row.item_name !== row.item_code) {
			item_html += `
				<br>
				<small class="text-muted">
					${escape_html(row.item_name)}
				</small>
			`;
		}

		let last_request_html = `
			<span class="text-muted">
				${__("Never")}
			</span>
		`;

		if (row.last_request_date) {
			const formatted_date = frappe.datetime.str_to_user(row.last_request_date);

			if (row.last_material_request) {
				last_request_html = `
					<a
						href="/app/material-request/${encodeURIComponent(row.last_material_request)}"
						target="_blank"
						title="${escape_html(row.last_material_request)}"
					>
						${formatted_date}
					</a>
				`;
			} else {
				last_request_html = formatted_date;
			}
		}

		const last_qty =
			row.last_request_qty !== null && row.last_request_qty !== undefined
				? format_qty(row.last_request_qty)
				: "-";

		const current_stock =
			row.current_stock !== null && row.current_stock !== undefined
				? format_qty(row.current_stock)
				: `
					<span
						class="text-muted"
						title="${__("Stock quantity could not be retrieved.")}"
					>
						-
					</span>
				`;

		let current_qty_style = "";

		if (row.last_request_qty !== null && row.last_request_qty !== undefined) {
			if (row.current_requested_qty > row.last_request_qty) {
				current_qty_style = "background-color: var(--red-50);";
			} else if (row.current_requested_qty < row.last_request_qty) {
				current_qty_style = "background-color: var(--green-50);";
			}
		}

		html += `
			<tr>
				<td>${item_html}</td>
				<td>${escape_html(row.target_warehouse)}</td>
				<td>${last_request_html}</td>
				<td class="text-right">${last_qty}</td>
				<td class="text-right"><b>${current_stock}</b></td>
				<td class="text-right" style="${current_qty_style}">
					<b>${format_qty(row.current_requested_qty)}</b>
				</td>
			</tr>
		`;
	});

	html += `
				</tbody>
			</table>
		</div>

		<div class="text-muted small">
			${__(
				"Last request is based on the same item and same target warehouse across submitted Material Issue and Material Transfer requests."
			)}
		</div>
	`;

	const dialog = new frappe.ui.Dialog({
		title: __("Material Request Review"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "review_html",
			},
		],
		primary_action_label: __("OK"),
		primary_action() {
			dialog.hide();
		},
	});

	dialog.fields_dict.review_html.$wrapper.html(html);
	dialog.show();
}

function format_qty(value) {
	return frappe.format(value || 0, {
		fieldtype: "Float",
		precision: 2,
	});
}

function escape_html(value) {
	return $("<div>").text(value || "").html();
}
