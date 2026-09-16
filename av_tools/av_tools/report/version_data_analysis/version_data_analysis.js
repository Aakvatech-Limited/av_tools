// Copyright (c) 2026, Aakvatech and contributors
// For license information, please see license.txt

frappe.query_reports["Version Data Analysis"] = {
	filters: [
		{
			fieldname: "analysis_mode",
			label: __("Analysis Mode"),
			fieldtype: "Select",
			options: ["DocType Summary", "Document Candidates", "Field Changes", "Owner Summary"],
			default: "DocType Summary",
			reqd: 1,
		},
		{
			fieldname: "cutover_date",
			label: __("Operational Cutover Date"),
			fieldtype: "Date",
			reqd: 1,
		},
		{
			fieldname: "before_days",
			label: __("Days Before Cutover"),
			fieldtype: "Int",
			default: 180,
			reqd: 1,
		},
		{
			fieldname: "after_days",
			label: __("Days After Cutover"),
			fieldtype: "Int",
			default: 180,
			reqd: 1,
		},
		{
			fieldname: "ref_doctype",
			label: __("DocType"),
			fieldtype: "Link",
			options: "DocType",
		},
		{
			fieldname: "owner",
			label: __("Version Owner"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "candidate_filter",
			label: __("Candidate Classification"),
			fieldtype: "Select",
			options: [
				"All",
				"Orphan Version History",
				"Pre-Cutover Only",
				"Active Across Cutover",
				"Post-Cutover Only",
			],
			default: "All",
			depends_on: "eval:doc.analysis_mode == 'Document Candidates'",
		},
		{
			fieldname: "max_versions",
			label: __("Max Versions"),
			fieldtype: "Int",
			default: 200000,
			description: __("Safety cap for Version rows scanned in one run."),
		},
	],
};
