frappe.query_reports["Bank Transaction Statement"] = {
    filters: [
        {fieldname: "company", label: "Company", fieldtype: "Link", options: "Company", reqd: 1, default: frappe.defaults.get_user_default("Company"),
            on_change: function(report) { report.set_filter_value("bank_account", ""); }},
        {fieldname: "bank_account", label: "Bank Account", fieldtype: "Link", options: "Bank Account", reqd: 1,
            get_query: function() { return {filters: {company: frappe.query_report.get_filter_value("company"), is_company_account: 1}}; }},
        {fieldname: "view", label: "View", fieldtype: "Select", options: ["Transaction Detail", "Monthly Summary"], default: "Transaction Detail", reqd: 1},
        {fieldname: "time_span", label: "Time Span", fieldtype: "Select", options: ["This Month", "Last Month", "This Year", "Last Year", "Period"], default: "This Month", reqd: 1},
        {fieldname: "from_date", label: "From Date", fieldtype: "Date", depends_on: "eval:doc.time_span == 'Period'"},
        {fieldname: "to_date", label: "To Date", fieldtype: "Date", depends_on: "eval:doc.time_span == 'Period'"}
    ],
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (data && (data.row_type === "Opening" || data.row_type === "Closing")) {
            value = "<strong>" + value + "</strong>";
        }
        return value;
    }
};
