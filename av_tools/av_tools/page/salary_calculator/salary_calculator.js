const salary_calculator_api = "av_tools.av_tools.page.salary_calculator.salary_calculator.";

frappe.pages["salary-calculator"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Salary Calculator"),
		single_column: true,
	});
	frappe.breadcrumbs.add("HR");
	new SalaryCalculatorPage(page);
};

class SalaryCalculatorPage {
	constructor(page) {
		this.page = page;
		this.fields = {};
		this.assignment_fields = [];
		this.context_revision = 0;
		this.calculation_revision = 0;
		this.render();
		this.create_fields();
	}

	$(selector) {
		return this.page.main.find(selector);
	}

	render() {
		this.page.main.addClass("salary-calculator-page").html(`
			<div class="sc-sheet">
				<section class="sc-section">
					<h4>${__("Calculation")}</h4>
					<div class="sc-fields"></div>
					<p class="sc-source text-muted" hidden></p>
					<div class="sc-assignment" hidden>
						<h5>${__("Assignment inputs")}</h5>
						<div class="sc-dynamic-fields"></div>
					</div>
				</section>
				<section class="sc-section sc-preview" aria-labelledby="sc-preview-title">
					<h4 id="sc-preview-title">${__("Salary slip preview")}</h4>
					<p class="sc-status text-muted" role="status"></p>
					<div class="sc-preview-content"></div>
				</section>
			</div>
		`);
	}

	add_field(df, parent = this.$(".sc-fields")) {
		const control = frappe.ui.form.make_control({
			df,
			parent: $("<div class='sc-field'></div>").appendTo(parent),
			render_input: true,
		});
		control.refresh();
		return control;
	}

	create_fields() {
		const fields = [
			{
				fieldname: "salary_structure",
				label: __("Salary Structure"),
				fieldtype: "Link",
				options: "Salary Structure",
				reqd: 1,
				change: () => this.load_assignment(),
				get_query: () => ({ filters: { is_active: "Yes", docstatus: 1 } }),
			},
			{
				fieldname: "employee",
				label: __("Employee"),
				fieldtype: "Link",
				options: "Employee",
				change: () => this.load_assignment(),
				get_query: () => ({
					filters: this.context ? { company: this.context.company } : {},
				}),
			},
			{
				fieldname: "mode",
				label: __("Calculate based on"),
				fieldtype: "Select",
				options: [
					{ label: __("Target net pay"), value: "Net Pay" },
					{ label: __("Target gross pay"), value: "Gross Pay" },
				],
				default: "Net Pay",
				change: () => this.change_mode(),
			},
			{
				fieldname: "target",
				label: __("Target net pay"),
				fieldtype: "Currency",
				reqd: 1,
				change: () => this.schedule_calculation(),
			},
			{
				fieldname: "from_date",
				label: __("Effective date"),
				fieldtype: "Date",
				default: frappe.datetime.get_today(),
				reqd: 1,
				change: () => this.load_assignment(),
			},
		];
		for (const df of fields) this.fields[df.fieldname] = this.add_field(df);
	}

	val(fieldname) {
		return this.fields[fieldname]?.get_value();
	}

	async change_mode() {
		if (!this.fields.target) return;
		const gross = this.val("mode") === "Gross Pay";
		const previous_amount = this.result?.[gross ? "gross_pay" : "net_pay"];
		this.fields.target.df.label = gross ? __("Target gross pay") : __("Target net pay");
		this.fields.target.refresh();
		if (previous_amount > 0) await this.fields.target.set_value(previous_amount);
		this.schedule_calculation();
	}

	async load_assignment() {
		const revision = ++this.context_revision;
		this.context = null;
		this.assignment_fields = [];
		this.$(".sc-assignment").prop("hidden", true);
		this.$(".sc-source").prop("hidden", true);
		this.$(".sc-dynamic-fields").empty();
		this.invalidate_calculation();
		const salary_structure = this.val("salary_structure");
		const from_date = this.val("from_date");
		if (!salary_structure || !from_date) return;
		this.set_status(__("Loading assignment inputs…"));
		try {
			const context = await frappe.xcall(salary_calculator_api + "get_assignment_inputs", {
				salary_structure,
				employee: this.val("employee"),
				from_date,
			});
			if (revision !== this.context_revision) return;

			const $fields = this.$(".sc-dynamic-fields");
			const controls = [];
			const values = [];
			for (const { value, ...df } of context.fields) {
				const control = this.add_field(
					{
						...df,
						options: df.fieldtype === "Currency" ? context.currency : undefined,
						precision:
							df.fieldtype === "Currency" && context.currency === "TZS"
								? 0
								: undefined,
						change: () => this.schedule_calculation(),
					},
					$fields
				);
				controls.push(control);
				values.push(control.set_value(value));
			}
			let tax_slab;
			if (this.val("employee")) {
				tax_slab = this.add_field(
					{
						fieldname: "income_tax_slab",
						label: __("Income Tax Slab"),
						fieldtype: "Link",
						options: "Income Tax Slab",
						change: () => this.schedule_calculation(),
						get_query: () => ({ filters: { company: context.company, docstatus: 1 } }),
					},
					$fields
				);
				values.push(tax_slab.set_value(context.income_tax_slab || ""));
			}
			await Promise.all(values);
			if (revision !== this.context_revision) return;

			this.context = context;
			this.assignment_fields = controls;
			this.tax_slab = tax_slab;
			this.fields.target.df.options = context.currency;
			this.fields.target.df.precision = context.currency === "TZS" ? 0 : undefined;
			this.fields.target.refresh();
			this.$(".sc-assignment").prop("hidden", !controls.length && !tax_slab);
			if (context.source) {
				this.$(".sc-source")
					.text(__("Source assignment {0}", [context.source]))
					.prop("hidden", false);
			}
			this.schedule_calculation();
		} catch {
			if (revision === this.context_revision)
				this.set_status(__("Could not load assignment inputs."), true);
		}
	}

	invalidate_calculation() {
		clearTimeout(this.calc_timer);
		this.calculation_revision++;
		this.result = null;
		this.page.clear_primary_action();
		this.$(".sc-status").insertAfter(this.$("#sc-preview-title"));
		this.$(".sc-preview-content").empty();
		this.set_status(__("Select a salary structure and enter a pay target."));
	}

	set_status(message, warning = false) {
		this.$(".sc-status")
			.text(message)
			.removeClass("sc-status-matched sc-status-estimate")
			.toggleClass("text-danger", warning)
			.toggleClass("text-muted", !warning);
	}

	schedule_calculation() {
		if (!this.context) return;
		this.invalidate_calculation();
		const revision = this.calculation_revision;
		if (!(flt(this.val("target")) > 0)) return;
		this.set_status(__("Calculating…"));
		this.calc_timer = setTimeout(() => this.calculate(revision), 250);
	}

	async calculate(revision) {
		const salary_structure = this.val("salary_structure");
		const employee = this.val("employee");
		const from_date = this.val("from_date");
		const calculate_based_on = this.val("mode") || "Net Pay";
		const target_field = calculate_based_on === "Gross Pay" ? "gross_pay" : "net_pay";
		const target_amount = flt(this.val("target"));
		const assignment_values = Object.fromEntries(
			this.assignment_fields.map((control) => [control.df.fieldname, control.get_value()])
		);
		const income_tax_slab = this.tax_slab ? this.tax_slab.get_value() || "" : undefined;
		const input = {
			salary_structure,
			employee,
			from_date,
			assignment_values,
			income_tax_slab,
		};
		try {
			const result = await frappe.xcall(salary_calculator_api + "run_calculation", {
				...input,
				calculate_based_on,
				[target_field]: target_amount,
			});
			if (revision !== this.calculation_revision) return;
			const html = await frappe.xcall(salary_calculator_api + "get_salary_slip_preview", {
				salary_structure,
				employee,
				base: result.base,
				gross_pay: result.gross_pay,
				net_pay: result.net_pay,
				earnings_data: result.earnings,
				deductions_data: result.deductions,
				employer_contributions: result.employer_contributions,
				total_deductions: result.total_deductions,
			});
			if (revision !== this.calculation_revision) return;

			this.result = result;
			this.$(".sc-preview-content").html(html);
			const success = result.target_matched && !result.estimated;
			const messages = [];
			if (result.estimated) messages.push(__("Estimate"));
			messages.push(
				result.target_matched
					? __("Target matched")
					: __("Target missed by {0}", [
							this.format_amount(Math.abs(target_amount - result[target_field])),
					  ])
			);
			const $status = this.$(".sc-status")
				.text(messages.join(" · "))
				.removeClass("text-muted text-danger")
				.toggleClass("sc-status-matched", success)
				.toggleClass("sc-status-estimate", !success);
			$status.appendTo(this.$(".sc-net"));
			if (success && employee) {
				const review = () =>
					this.review_assignment(
						{
							...input,
							base: result.base,
							target: { field: target_field, amount: target_amount },
						},
						revision,
						result
					);
				this.page.set_primary_action(__("Review assignment"), review);
				$('<button class="btn btn-primary sc-mobile-review"></button>')
					.text(__("Review assignment"))
					.on("click", review)
					.insertAfter(this.$(".sc-summary"));
			}
		} catch {
			if (revision === this.calculation_revision)
				this.set_status(__("Could not calculate this salary."), true);
		}
	}

	format_amount(amount) {
		const currency = this.context.currency;
		return format_currency(amount, currency, currency === "TZS" ? 0 : undefined);
	}

	review_assignment(input, revision, result) {
		if (revision !== this.calculation_revision) return;
		const dialog = new frappe.ui.Dialog({
			title: __("Review Salary Structure Assignment"),
			fields: [{ fieldname: "summary", fieldtype: "HTML" }],
			primary_action_label: __("Create & Submit"),
			primary_action: async () => {
				if (revision !== this.calculation_revision) {
					frappe.msgprint(
						__(
							"The calculation changed. Review the current preview before submitting."
						)
					);
					return;
				}
				const $button = dialog.get_primary_btn().prop("disabled", true);
				try {
					const name = await frappe.xcall(
						salary_calculator_api + "create_salary_structure_assignment",
						input
					);
					dialog.hide();
					frappe.set_route("Form", "Salary Structure Assignment", name);
				} catch {
					// The server displays the payroll validation error.
				} finally {
					$button.prop("disabled", false);
				}
			},
		});
		const items = [
			[__("Employee"), input.employee],
			[__("Salary Structure"), input.salary_structure],
			[__("Effective date"), frappe.datetime.str_to_user(input.from_date)],
			[__("Assignment base"), this.format_amount(result.base)],
			[__("Calculated net pay"), this.format_amount(result.net_pay)],
		];
		if (input.income_tax_slab) items.push([__("Income Tax Slab"), input.income_tax_slab]);
		for (const { df } of this.assignment_fields) {
			const value = input.assignment_values[df.fieldname];
			const label =
				df.fieldtype === "Check"
					? cint(value)
						? __("Yes")
						: __("No")
					: df.fieldtype === "Currency"
					? this.format_amount(value)
					: cstr(value);
			items.push([df.label, label]);
		}
		const $summary = $("<dl class='sc-totals'></dl>");
		for (const [label, value] of items) {
			$("<div></div>")
				.append($("<dt></dt>").text(label), $("<dd></dd>").text(value))
				.appendTo($summary);
		}
		dialog.fields_dict.summary.$wrapper.empty().append($summary);
		dialog.show();
	}
}
