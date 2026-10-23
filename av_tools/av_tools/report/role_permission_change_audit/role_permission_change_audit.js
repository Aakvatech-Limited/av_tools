const permissionFields = [
    "select", "read", "write", "create", "delete", "submit",
    "cancel", "amend", "report", "export", "import", "share",
    "print", "email", "mask", "impersonate", "if_owner",
];

frappe.query_reports["Role Permission Change Audit"] = {
    filters: [
        {
            fieldname: "time_span", label: "Time Span", fieldtype: "Select",
            options: ["Today", "Yesterday", "This Week", "Last Week", "Last 7 Days", "This Month", "Last Month", "Period"],
            default: "Last 7 Days", reqd: 1,
        },
        {
            fieldname: "from_date", label: "From Date", fieldtype: "Date",
            depends_on: "eval:doc.time_span == 'Period'",
            mandatory_depends_on: "eval:doc.time_span == 'Period'",
        },
        {
            fieldname: "to_date", label: "To Date", fieldtype: "Date",
            depends_on: "eval:doc.time_span == 'Period'",
            mandatory_depends_on: "eval:doc.time_span == 'Period'",
        },
        {fieldname: "role", label: "Role", fieldtype: "Link", options: "Role"},
        {fieldname: "doctype_name", label: "DocType", fieldtype: "Link", options: "DocType"},
        {fieldname: "changed_by", label: "Changed By", fieldtype: "Link", options: "User"},
        {
            fieldname: "action", label: "Action", fieldtype: "Select",
            options: ["All", "Added", "Removed", "Updated", "Created", "Deleted"], default: "All",
        },
        {
            fieldname: "permission", label: "Permission", fieldtype: "Select",
            options: ["", ...permissionFields],
        },
    ],
    formatter(value, row, column, data, default_formatter) {
        const formatted = default_formatter(value, row, column, data);
        if (!column || !permissionFields.includes(column.fieldname)) {
            return formatted;
        }
        const status = String(value || "").toLowerCase();
        const palette = {
            added: ["var(--bg-green, #e2f5e9)", "var(--text-on-green, #176b40)"],
            removed: ["var(--bg-red, #fde8e8)", "var(--text-on-red, #a32424)"],
            changed: ["var(--bg-orange, #fff1d6)", "var(--text-on-orange, #935500)"],
        };
        if (!palette[status]) {
            return formatted;
        }
        const [background, color] = palette[status];
        const label = status.charAt(0).toUpperCase() + status.slice(1);
        return '<span style="display:inline-block;padding:3px 9px;border-radius:5px;'
            + 'background:' + background + ';color:' + color + ' !important;'
            + 'font-weight:700;font-size:11px;white-space:nowrap;">'
            + label + '</span>';
    },
};
