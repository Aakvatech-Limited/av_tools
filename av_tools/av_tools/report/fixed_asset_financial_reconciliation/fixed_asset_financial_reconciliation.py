"""Asset financial reconciliation, ported from the inspected live report (2026-10-18)."""

import frappe

from av_tools.asset_reconciliation.permissions import run_permitted


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		frappe.throw("Company is required.")
	frappe.get_doc("Company", filters.company).check_permission("read")
	group_name = filters.get("depreciation_group_account")
	if not group_name:
		frappe.throw("Depreciation Group Account is required.")
	group_account = frappe.get_doc("Account", group_name)
	group_account.check_permission("read")
	if group_account.company != filters.company or not group_account.is_group:
		frappe.throw("Select a group Account belonging to the selected company.")
	# Nested-set boundaries include descendants at every depth.
	depreciation_accounts = frappe.get_list(
		"Account",
		filters={
			"company": filters.company,
			"lft": [">", group_account.lft],
			"rgt": ["<", group_account.rgt],
			"is_group": 0,
		},
		pluck="name",
		limit_page_length=0,
	)
	if not depreciation_accounts:
		frappe.throw("The selected Depreciation Group Account has no accessible ledger accounts.")
	permission_cache = {}
	company = filters.get("company") or frappe.defaults.get_user_default("Company")
	as_on = filters.get("as_on") or frappe.utils.today()
	tolerance = 1.0
	columns = [
		{"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 190},
		{
			"fieldname": "reference_date",
			"label": "Asset Use / Voucher Date",
			"fieldtype": "Date",
			"width": 160,
		},
		{"fieldname": "asset", "label": "Asset", "fieldtype": "Link", "options": "Asset", "width": 180},
		{"fieldname": "asset_name", "label": "Asset Name", "fieldtype": "Data", "width": 230},
		{"fieldname": "asset_category", "label": "Category", "fieldtype": "Data", "width": 130},
		{
			"fieldname": "schedule",
			"label": "Depreciation Schedule",
			"fieldtype": "Link",
			"options": "Asset Depreciation Schedule",
			"width": 200,
		},
		{"fieldname": "expected", "label": "Scheduled Due", "fieldtype": "Currency", "width": 135},
		{"fieldname": "booked", "label": "Scheduled JE Amount", "fieldtype": "Currency", "width": 150},
		{"fieldname": "difference", "label": "Due Less Booked", "fieldtype": "Currency", "width": 145},
		{"fieldname": "gl_debit", "label": "Depreciation GL Debit", "fieldtype": "Currency", "width": 155},
		{
			"fieldname": "gl_credit",
			"label": "Accumulated Dep GL Credit",
			"fieldtype": "Currency",
			"width": 165,
		},
		{
			"fieldname": "gl_difference",
			"label": "GL Posting Difference",
			"fieldtype": "Currency",
			"width": 150,
		},
		{"fieldname": "purchase_amount", "label": "Asset Cost", "fieldtype": "Currency", "width": 130},
		{"fieldname": "notes", "label": "Exception / Detail", "fieldtype": "Data", "width": 370},
		{
			"fieldname": "purchase_invoice",
			"label": "Purchase Invoice",
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 180,
		},
		{"fieldname": "capital_account", "label": "Capital Asset Account", "fieldtype": "Data", "width": 200},
		{"fieldname": "capital_gl", "label": "Capital GL Net", "fieldtype": "Currency", "width": 145},
		{"fieldname": "purchase_variance", "label": "Cost vs GL", "fieldtype": "Currency", "width": 135},
		{"fieldname": "mapped_cost", "label": "Approved Mapped Cost", "fieldtype": "Currency", "width": 165},
		{"fieldname": "unmapped_cost", "label": "Asset Cost Unmapped", "fieldtype": "Currency", "width": 160},
		{
			"fieldname": "unallocated_capital",
			"label": "Unallocated Capital GL",
			"fieldtype": "Currency",
			"width": 175,
		},
		{
			"fieldname": "reconciliation",
			"label": "Asset Capitalization Reconciliation",
			"fieldtype": "Link",
			"options": "Asset Capitalization Reconciliation",
			"width": 230,
		},
		{"fieldname": "reconciliation_status", "label": "Mapping Status", "fieldtype": "Data", "width": 120},
		{
			"fieldname": "other_reconciliations",
			"label": "Additional Mapping References",
			"fieldtype": "Data",
			"width": 210,
		},
	]
	Asset = frappe.qb.DocType("Asset")
	Schedule = frappe.qb.DocType("Asset Depreciation Schedule")
	Detail = frappe.qb.DocType("Depreciation Schedule")
	GL = frappe.qb.DocType("GL Entry")
	JE = frappe.qb.DocType("Journal Entry")
	assets = run_permitted(
		frappe.qb.from_(Asset)
		.select(
			Asset.name,
			Asset.asset_name,
			Asset.asset_category,
			Asset.total_asset_cost,
			Asset.calculate_depreciation,
			Asset.purchase_date,
			Asset.available_for_use_date,
			Asset.disposal_date,
		)
		.where(Asset.docstatus == 1)
		.where(Asset.company == company)
		.where(Asset.status != "Scrapped"),
		"Asset",
		permission_cache,
	)
	schedules = run_permitted(
		frappe.qb.from_(Schedule)
		.select(Schedule.name, Schedule.asset, Schedule.docstatus)
		.where(Schedule.company == company)
		.where(Schedule.docstatus == 1),
		"Asset Depreciation Schedule",
		permission_cache,
	)
	schedule_names = [x.name for x in schedules]
	details = []
	if schedule_names:
		details = run_permitted(
			frappe.qb.from_(Detail)
			.select(Detail.parent, Detail.schedule_date, Detail.depreciation_amount, Detail.journal_entry)
			.where(Detail.parent.isin(schedule_names)),
			"Depreciation Schedule",
			permission_cache,
		)
	journal_names = list({d.journal_entry for d in details if d.journal_entry})
	journal_status = {}
	if journal_names:
		journals = run_permitted(
			frappe.qb.from_(JE).select(JE.name, JE.docstatus).where(JE.name.isin(journal_names)),
			"Journal Entry",
			permission_cache,
		)
		for j in journals:
			journal_status[j.name] = j.docstatus
	scrapped_assets = run_permitted(
		frappe.qb.from_(Asset)
		.select(Asset.name, Asset.journal_entry_for_scrap)
		.where(Asset.company == company)
		.where(Asset.status == "Scrapped"),
		"Asset",
		permission_cache,
	)
	scrapped_asset_ids = {a.name for a in scrapped_assets}
	scrap_journals = {a.journal_entry_for_scrap for a in scrapped_assets if a.journal_entry_for_scrap}
	gl_rows = run_permitted(
		frappe.qb.from_(GL)
		.select(
			GL.voucher_no,
			GL.voucher_type,
			GL.account,
			GL.debit,
			GL.credit,
			GL.posting_date,
			GL.against_voucher,
		)
		.where(GL.company == company)
		.where(GL.posting_date <= as_on)
		.where(GL.is_cancelled == 0)
		.where(GL.voucher_type == "Journal Entry")
		.where(GL.account.isin(depreciation_accounts)),
		"GL Entry",
		permission_cache,
		permission_filters={
			"company": company,
			"posting_date": ["<=", as_on],
			"is_cancelled": 0,
			"voucher_type": "Journal Entry",
			"account": ["in", depreciation_accounts],
		},
	)
	gl_map = {}
	for g in gl_rows:
		if g.against_voucher in scrapped_asset_ids or g.voucher_no in scrap_journals:
			continue
		account = (g.account or "").lower()
		if g.voucher_type != "Journal Entry":
			continue
		if g.voucher_no not in gl_map:
			gl_map[g.voucher_no] = {"debit": 0.0, "credit": 0.0}
		if "accumulated" in account:
			gl_map[g.voucher_no]["credit"] = (
				gl_map[g.voucher_no]["credit"] + float(g.credit or 0) - float(g.debit or 0)
			)
		else:
			gl_map[g.voucher_no]["debit"] = (
				gl_map[g.voucher_no]["debit"] + float(g.debit or 0) - float(g.credit or 0)
			)
	detail_by_schedule = {}
	for d in details:
		if d.parent not in detail_by_schedule:
			detail_by_schedule[d.parent] = []
		detail_by_schedule[d.parent].append(d)
	schedule_by_asset = {}
	for s in schedules:
		if s.asset not in schedule_by_asset:
			schedule_by_asset[s.asset] = []
		schedule_by_asset[s.asset].append(s)
	linked_journals = set()
	data = []
	for a in assets:
		linked = schedule_by_asset.get(a.name, [])
		due = 0.0
		booked = 0.0
		debit = 0.0
		credit = 0.0
		issues = []
		schedule_names_text = []
		for s in linked:
			schedule_names_text.append(s.name)
			for d in detail_by_schedule.get(s.name, []):
				if d.schedule_date and str(d.schedule_date) <= str(as_on):
					due = due + float(d.depreciation_amount or 0)
					if d.journal_entry and journal_status.get(d.journal_entry) == 1:
						booked = booked + float(d.depreciation_amount or 0)
						if d.journal_entry not in linked_journals:
							linked_journals.add(d.journal_entry)
							v = gl_map.get(d.journal_entry, {})
							debit = debit + float(v.get("debit", 0))
							credit = credit + float(v.get("credit", 0))
					else:
						issues.append("Due schedule row has no submitted depreciation JE")
		if a.calculate_depreciation and (not linked):
			issues.append("No submitted Asset Depreciation Schedule")
		if not a.calculate_depreciation:
			issues.append("Asset not configured for depreciation")
		difference = due - booked
		gl_difference = debit - credit
		if abs(difference) > tolerance:
			issues.append("Scheduled depreciation not fully posted")
		if abs(gl_difference) > tolerance:
			issues.append("Depreciation GL debit/credit imbalance")
		if booked and abs(booked - debit) > tolerance:
			issues.append("Booked schedule does not agree with depreciation GL debit")
		if booked and abs(booked - credit) > tolerance:
			issues.append("Booked schedule does not agree with accumulated depreciation GL credit")
		status = "Exception" if issues else "OK"
		if not linked and (not a.calculate_depreciation):
			status = "Review - nondepreciable"
		data.append(
			{
				"status": status,
				"asset": a.name,
				"asset_name": a.asset_name,
				"asset_category": a.asset_category,
				"schedule": schedule_names_text[0] if schedule_names_text else "",
				"expected": due,
				"booked": booked,
				"difference": difference,
				"gl_debit": debit,
				"gl_credit": credit,
				"gl_difference": gl_difference,
				"purchase_amount": a.total_asset_cost,
				"notes": "; ".join(issues),
			}
		)
	for je_name in gl_map:
		if je_name not in linked_journals:
			amounts = gl_map[je_name]
			data.append(
				{
					"status": "Unmatched depreciation GL",
					"_voucher_key": "Journal Entry|" + je_name,
					"asset": "",
					"asset_name": "",
					"asset_category": "",
					"schedule": "",
					"expected": 0,
					"booked": 0,
					"difference": 0,
					"gl_debit": amounts["debit"],
					"gl_credit": amounts["credit"],
					"gl_difference": amounts["debit"] - amounts["credit"],
					"purchase_amount": 0,
					"notes": "Depreciation-related journal "
					+ je_name
					+ " has no due submitted schedule link; review manual adjustments and period closing vouchers",
				}
			)
	Category = frappe.qb.DocType("Asset Category")
	CA = frappe.qb.DocType("Asset Category Account")
	capital_accounts = set()
	ca_rows = run_permitted(
		frappe.qb.from_(Category)
		.join(CA)
		.on(CA.parent == Category.name)
		.select(Category.name, CA.company_name, CA.fixed_asset_account)
		.where(CA.company_name == company),
		"Asset Category",
		permission_cache,
	)
	account_by_category = {}
	for c in ca_rows:
		if c.fixed_asset_account:
			account_by_category[c.name] = c.fixed_asset_account
			capital_accounts.add(c.fixed_asset_account)
	capital_rows = []
	if capital_accounts:
		capital_rows = run_permitted(
			frappe.qb.from_(GL)
			.select(GL.voucher_type, GL.voucher_no, GL.account, GL.debit, GL.credit, GL.posting_date)
			.where(GL.company == company)
			.where(GL.is_cancelled == 0)
			.where(GL.posting_date <= as_on)
			.where(GL.account.isin(capital_accounts)),
			"GL Entry",
			permission_cache,
			permission_filters={
				"company": company,
				"posting_date": ["<=", as_on],
				"is_cancelled": 0,
				"account": ["in", list(capital_accounts)],
			},
		)
	capital_vouchers = {}
	for g in capital_rows:
		if g.voucher_no in scrap_journals:
			continue
		key = (g.voucher_type or "") + "|" + (g.voucher_no or "")
		if key not in capital_vouchers:
			capital_vouchers[key] = {
				"amount": 0.0,
				"account": g.account,
				"type": g.voucher_type,
				"voucher": g.voucher_no,
			}
		capital_vouchers[key]["amount"] = (
			capital_vouchers[key]["amount"] + float(g.debit or 0) - float(g.credit or 0)
		)
	assets_by_invoice = {}
	assets_by_name = {}
	for a in assets:
		assets_by_name[a.name] = a
	purchases = run_permitted(
		frappe.qb.from_(Asset)
		.select(
			Asset.name,
			Asset.purchase_invoice,
			Asset.purchase_invoice_item,
			Asset.av_nta_purchase_invoice,
			Asset.av_nta_purchase_invoice_item,
			Asset.asset_category,
			Asset.total_asset_cost,
			Asset.purchase_amount,
			Asset.asset_quantity,
		)
		.where(Asset.company == company)
		.where(Asset.docstatus == 1)
		.where(Asset.status != "Scrapped"),
		"Asset",
		permission_cache,
	)
	asset_purchase = {}
	for a in purchases:
		a.purchase_invoice = a.purchase_invoice or a.av_nta_purchase_invoice
		a.purchase_invoice_item = a.purchase_invoice_item or a.av_nta_purchase_invoice_item
		asset_purchase[a.name] = a
		if a.purchase_invoice:
			if a.purchase_invoice not in assets_by_invoice:
				assets_by_invoice[a.purchase_invoice] = []
			assets_by_invoice[a.purchase_invoice].append(a.name)
	for row in data:
		if row.get("asset"):
			info = asset_purchase.get(row["asset"])
			if info:
				row["purchase_invoice"] = info.purchase_invoice
				row["capital_account"] = account_by_category.get(info.asset_category) or ""
				if info.purchase_invoice:
					key = "Purchase Invoice|" + info.purchase_invoice
					if key in capital_vouchers:
						row["capital_gl"] = capital_vouchers[key]["amount"]
						if len(assets_by_invoice.get(info.purchase_invoice, [])) == 1:
							row["purchase_variance"] = float(info.total_asset_cost or 0) - row["capital_gl"]
							if abs(row["purchase_variance"]) > tolerance:
								row["notes"] = (
									(row.get("notes") or "")
									+ "; Cost differs from direct invoice capitalization; inspect tax/landed costs"
								)
					else:
						row["notes"] = (
							(row.get("notes") or "")
							+ "; No direct fixed-asset GL posting on linked Purchase Invoice; check capitalization JE or receipt"
						)
				else:
					row["notes"] = (
						row.get("notes") or ""
					) + "; Purchase Invoice not specified; acquisition trace incomplete"
	for key in capital_vouchers:
		v = capital_vouchers[key]
		if abs(v["amount"]) <= tolerance:
			continue
		if v["type"] == "Purchase Invoice":
			associated = assets_by_invoice.get(v["voucher"], [])
			if not associated:
				data.append(
					{
						"status": "Acquisition not matched to Asset",
						"asset": "",
						"asset_name": "",
						"asset_category": "",
						"schedule": "",
						"expected": 0,
						"booked": 0,
						"difference": 0,
						"gl_debit": 0,
						"gl_credit": 0,
						"gl_difference": 0,
						"purchase_amount": 0,
						"purchase_invoice": v["voucher"],
						"capital_account": v["account"],
						"capital_gl": v["amount"],
						"purchase_variance": 0,
						"notes": "Submitted fixed-asset GL posting from Purchase Invoice has no Asset with matching purchase_invoice; investigate capitalization and source lines",
					}
				)
		else:
			data.append(
				{
					"status": "Capital GL reference for review",
					"_voucher_key": key,
					"asset": "",
					"asset_name": "",
					"asset_category": "",
					"schedule": "",
					"expected": 0,
					"booked": 0,
					"difference": 0,
					"gl_debit": 0,
					"gl_credit": 0,
					"gl_difference": 0,
					"purchase_amount": 0,
					"purchase_invoice": "",
					"capital_account": v["account"],
					"capital_gl": v["amount"],
					"purchase_variance": 0,
					"notes": "Fixed-asset account movement in "
					+ v["type"]
					+ " "
					+ v["voucher"]
					+ "; match to Asset capitalization, disposal, transfer or opening balances",
				}
			)
	Map = frappe.qb.DocType("Asset Capitalization Reconciliation")
	MapAsset = frappe.qb.DocType("Asset Reconciliation Asset")
	MapSource = frappe.qb.DocType("Asset Reconciliation Source")
	groups = run_permitted(
		frappe.qb.from_(Map)
		.select(Map.name, Map.company, Map.status)
		.where(Map.company == company)
		.where(Map.status == "Approved"),
		"Asset Capitalization Reconciliation",
		permission_cache,
	)
	group_names = [x.name for x in groups]
	mapped_assets = {}
	mapped_vouchers = {}
	if group_names:
		alloc_assets = run_permitted(
			frappe.qb.from_(MapAsset)
			.select(MapAsset.parent, MapAsset.asset, MapAsset.allocated_amount)
			.where(MapAsset.parent.isin(group_names)),
			"Asset Reconciliation Asset",
			permission_cache,
		)
		alloc_sources = run_permitted(
			frappe.qb.from_(MapSource)
			.select(
				MapSource.parent,
				MapSource.gl_entry,
				MapSource.source_voucher_type,
				MapSource.source_voucher,
				MapSource.source_line,
				MapSource.allocated_amount,
			)
			.where(MapSource.parent.isin(group_names)),
			"Asset Reconciliation Source",
			permission_cache,
		)
		group_asset_sum = {}
		group_source_sum = {}
		for a in alloc_assets:
			group_asset_sum[a.parent] = group_asset_sum.get(a.parent, 0) + float(a.allocated_amount or 0)
		for s in alloc_sources:
			group_source_sum[s.parent] = group_source_sum.get(s.parent, 0) + float(s.allocated_amount or 0)
		balanced_groups = set()
		for g in groups:
			if (
				group_asset_sum.get(g.name, 0) > 0
				and abs(group_asset_sum.get(g.name, 0) - group_source_sum.get(g.name, 0)) <= tolerance
			):
				balanced_groups.add(g.name)
		for a in alloc_assets:
			if a.parent in balanced_groups:
				mapped_assets[a.asset] = mapped_assets.get(a.asset, 0) + float(a.allocated_amount or 0)
		PIItem = frappe.qb.DocType("Purchase Invoice Item")
		invoice_names = {
			source.source_voucher
			for source in alloc_sources
			if source.parent in balanced_groups
			and source.source_voucher_type == "Purchase Invoice"
			and source.source_voucher
		}
		item_accounts = {}
		if invoice_names:
			invoice_items = run_permitted(
				frappe.qb.from_(PIItem)
				.select(PIItem.name, PIItem.parent, PIItem.expense_account)
				.where(PIItem.parent.isin(invoice_names)),
				"Purchase Invoice Item",
				permission_cache,
			)
			for item in invoice_items:
				item_accounts[item.name] = item.expense_account
		for s in alloc_sources:
			if s.parent in balanced_groups and s.source_voucher_type and s.source_voucher:
				eligible = True
				if s.source_voucher_type == "Purchase Invoice" and s.source_line:
					account = item_accounts.get(s.source_line)
					if account not in capital_accounts:
						eligible = False
				if eligible:
					source_key = s.source_voucher_type + "|" + s.source_voucher
					mapped_vouchers[source_key] = mapped_vouchers.get(source_key, 0) + float(
						s.allocated_amount or 0
					)
	for row in data:
		if row.get("asset"):
			a = asset_purchase.get(row["asset"])
			if a:
				mapped = mapped_assets.get(row["asset"], 0)
				row["mapped_cost"] = mapped
				row["unmapped_cost"] = float(a.total_asset_cost or 0) - mapped
				if mapped and abs(row["unmapped_cost"]) <= tolerance:
					if row.get("notes"):
						row["notes"] = row["notes"] + "; Approved capitalization mapping covers asset cost"
					else:
						row["notes"] = "Approved capitalization mapping covers asset cost"
					if row.get("status") == "OK":
						row["status"] = "Mapped / Depreciation OK"
		if row.get("status") == "Acquisition not matched to Asset":
			k = "Purchase Invoice|" + (row.get("purchase_invoice") or "")
			mapped_amount = mapped_vouchers.get(k, 0)
			row["unallocated_capital"] = float(row.get("capital_gl") or 0) - mapped_amount
			if mapped_amount > 0:
				row["status"] = (
					"Partially reconciled acquisition"
					if abs(row["unallocated_capital"]) > tolerance
					else "Acquisition matched by approved mapping"
				)
				row["notes"] = (row.get("notes") or "") + "; Approved allocation " + str(mapped_amount)
		if row.get("status") == "Capital GL reference for review":
			key = row.get("_voucher_key")
			if key:
				amt = mapped_vouchers.get(key, 0)
				row["unallocated_capital"] = float(row.get("capital_gl") or 0) - amt
				if amt > 0:
					row["status"] = (
						"Capital GL matched by mapping"
						if abs(row["unallocated_capital"]) <= tolerance
						else "Partially reconciled capital GL"
					)
	all_maps = run_permitted(
		frappe.qb.from_(Map).select(Map.name, Map.status).where(Map.company == company),
		"Asset Capitalization Reconciliation",
		permission_cache,
	)
	all_map_names = [m.name for m in all_maps]
	asset_references = {}
	voucher_references = {}
	asset_reference_seen = {}
	voucher_reference_seen = {}
	if all_map_names:
		all_map_assets = run_permitted(
			frappe.qb.from_(MapAsset)
			.select(MapAsset.parent, MapAsset.asset)
			.where(MapAsset.parent.isin(all_map_names)),
			"Asset Reconciliation Asset",
			permission_cache,
		)
		all_map_sources = run_permitted(
			frappe.qb.from_(MapSource)
			.select(MapSource.parent, MapSource.source_voucher_type, MapSource.source_voucher)
			.where(MapSource.parent.isin(all_map_names)),
			"Asset Reconciliation Source",
			permission_cache,
		)
		map_status = {}
		for m in all_maps:
			map_status[m.name] = m.status
		for a in all_map_assets:
			if a.asset:
				if a.asset not in asset_references:
					asset_references[a.asset] = []
				seen = asset_reference_seen.setdefault(a.asset, set())
				if a.parent not in seen:
					asset_references[a.asset].append(a.parent)
					seen.add(a.parent)
		for v in all_map_sources:
			if v.source_voucher_type and v.source_voucher:
				key = v.source_voucher_type + "|" + v.source_voucher
				if key not in voucher_references:
					voucher_references[key] = []
				seen = voucher_reference_seen.setdefault(key, set())
				if v.parent not in seen:
					voucher_references[key].append(v.parent)
					seen.add(v.parent)
	for row in data:
		refs = []
		if row.get("asset"):
			refs = asset_references.get(row["asset"], [])
		elif row.get("purchase_invoice"):
			refs = voucher_references.get("Purchase Invoice|" + row["purchase_invoice"], [])
		elif row.get("status") in [
			"Capital GL reference for review",
			"Capital GL matched by mapping",
			"Partially reconciled capital GL",
		]:
			voucher_key = row.get("_voucher_key")
			if voucher_key:
				refs = voucher_references.get(voucher_key, [])
		if refs:
			row["reconciliation"] = refs[0]
			row["reconciliation_status"] = map_status.get(refs[0]) or ""
			row["other_reconciliations"] = ", ".join(refs[1:])
	direct_invoice_assets = {}
	direct_invoice_refs = []
	for asset_record in purchases:
		if asset_record.purchase_invoice and asset_record.purchase_invoice_item:
			direct_invoice_refs.append(asset_record.purchase_invoice)
	direct_invoice_refs = list(set(direct_invoice_refs))
	if direct_invoice_refs:
		PI = frappe.qb.DocType("Purchase Invoice")
		PII = frappe.qb.DocType("Purchase Invoice Item")
		invoice_headers = run_permitted(
			frappe.qb.from_(PI).select(PI.name, PI.docstatus).where(PI.name.isin(direct_invoice_refs)),
			"Purchase Invoice",
			permission_cache,
		)
		valid_invoice_names = []
		for hdr in invoice_headers:
			if hdr.docstatus == 1:
				valid_invoice_names.append(hdr.name)
		if valid_invoice_names:
			item_rows = run_permitted(
				frappe.qb.from_(PII)
				.select(PII.name, PII.parent, PII.expense_account, PII.base_net_amount, PII.qty)
				.where(PII.parent.isin(valid_invoice_names)),
				"Purchase Invoice Item",
				permission_cache,
			)
			items_by_id = {}
			for inv_item in item_rows:
				items_by_id[inv_item.name] = inv_item
			quantity_by_line = {}
			for asset_record in purchases:
				line = asset_record.purchase_invoice_item
				quantity_by_line[line] = quantity_by_line.get(line, 0) + float(
					asset_record.asset_quantity or 1
				)
			for asset_record in purchases:
				inv_item = items_by_id.get(asset_record.purchase_invoice_item)
				if inv_item and inv_item.parent == asset_record.purchase_invoice:
					category_account = account_by_category.get(asset_record.asset_category)
					if (
						category_account
						and inv_item.expense_account == category_account
						and float(inv_item.qty or 0) > 0
						and quantity_by_line.get(inv_item.name, 0) <= float(inv_item.qty)
					):
						direct_invoice_assets[asset_record.name] = (
							float(inv_item.base_net_amount or 0)
							* float(asset_record.asset_quantity or 1)
							/ float(inv_item.qty)
						)
	for report_row in data:
		asset_id = report_row.get("asset")
		if asset_id in direct_invoice_assets:
			direct_cost = direct_invoice_assets[asset_id]
			actual_cost = float(report_row.get("purchase_amount") or 0)
			if abs(direct_cost - actual_cost) <= tolerance:
				approved = float(report_row.get("mapped_cost") or 0)
				if approved < actual_cost:
					report_row["mapped_cost"] = actual_cost
					report_row["unmapped_cost"] = 0
					report_row["notes"] = (
						(report_row.get("notes") or "")
						+ "; Direct Purchase Invoice item capitalization verified"
					).strip("; ")
	asset_dates = {}
	for asset_row in assets:
		asset_dates[asset_row.name] = asset_row.available_for_use_date or asset_row.purchase_date
	voucher_dates = {}
	for gl_row in capital_rows:
		voucher_key = (gl_row.voucher_type or "") + "|" + (gl_row.voucher_no or "")
		if voucher_key not in voucher_dates or str(gl_row.posting_date) < str(voucher_dates[voucher_key]):
			voucher_dates[voucher_key] = gl_row.posting_date
	depreciation_voucher_dates = {}
	for gl_row in gl_rows:
		if (
			gl_row.voucher_no not in depreciation_voucher_dates
			or gl_row.posting_date < depreciation_voucher_dates[gl_row.voucher_no]
		):
			depreciation_voucher_dates[gl_row.voucher_no] = gl_row.posting_date
	for result_row in data:
		if result_row.get("asset"):
			result_row["reference_date"] = asset_dates.get(result_row["asset"])
		elif result_row.get("purchase_invoice"):
			result_row["reference_date"] = voucher_dates.get(
				"Purchase Invoice|" + result_row["purchase_invoice"]
			)
		elif result_row.get("status") == "Unmatched depreciation GL":
			result_row["reference_date"] = depreciation_voucher_dates.get(
				(result_row.get("_voucher_key") or "").partition("|")[2]
			)
		else:
			result_row["reference_date"] = voucher_dates.get(result_row.get("_voucher_key"))
	if (filters.get("view_mode") or "Exceptions Only") == "Exceptions Only":
		filtered_data = []
		for row in data:
			status = row.get("status") or ""
			mapped_amount = float(row.get("mapped_cost") or 0)
			asset_cost = float(row.get("purchase_amount") or 0)
			if status in ["Acquisition matched by approved mapping", "Capital GL matched by mapping"]:
				continue
			if status in ["OK", "Mapped / Depreciation OK"]:
				if abs(asset_cost - mapped_amount) <= tolerance:
					continue
				row["status"] = "Asset cost not fully mapped"
				row["unmapped_cost"] = asset_cost - mapped_amount
			if status == "Review - nondepreciable":
				if abs(asset_cost - mapped_amount) <= tolerance:
					continue
			if status in ["Partially reconciled acquisition", "Partially reconciled capital GL"]:
				outstanding = float(row.get("unallocated_capital") or 0)
				if abs(outstanding) <= tolerance:
					continue
				row["capital_gl"] = outstanding
			filtered_data.append(row)
		data = filtered_data
	for row in data:
		row.pop("_voucher_key", None)
	return (columns, data)
