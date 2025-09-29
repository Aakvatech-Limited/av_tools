import frappe
from frappe.utils.safe_exec import safe_exec
from frappe.core.doctype.report.report import Report


class ReportOverride(Report):
    """Override Report class to support Python code override from Report Extension"""
    
    def execute_script_report(self, filters):
        """Override script report execution to check for Report Extension Python override"""
        
        # Check if there's an active Report Extension with Python override
        if frappe.db.exists("Report Extension", self.name):
            av_report_extension_doc = frappe.get_doc("Report Extension", self.name)
            
            if av_report_extension_doc.active and av_report_extension_doc.script_python:
                # Execute the custom Python script instead of the original report
                frappe.log_error(f"Executing Python override for report: {self.name}", "Report Extension")
                return self.execute_custom_python_script(av_report_extension_doc.script_python, filters)
        
        # Fall back to original script report execution
        return super().execute_script_report(filters)
    
    def execute_custom_python_script(self, script_python, filters):
        """Execute custom Python script for report override"""
        try:
            # Prepare the execution context similar to how Frappe handles script reports
            loc = {
                "filters": frappe._dict(filters) if filters else frappe._dict(),
                "data": None,
                "result": None,
                "columns": None,
                "message": None,
                "chart": None,
                "report_summary": None,
                "skip_total_row": None
            }
            
            # Execute the custom script using safe_exec
            safe_exec(script_python, None, loc, script_filename=f"Report Extension {self.name}")
            
            # Return results in the expected format (same as Report.execute_script)
            if loc["data"]:
                # If data is returned, it should be in the format [columns, result, message, chart, report_summary, skip_total_row]
                return loc["data"]
            else:
                # Return individual components - follow the same pattern as execute_script
                columns = loc.get("columns", [])
                result = loc.get("result", [])
                message = loc.get("message")
                chart = loc.get("chart")
                report_summary = loc.get("report_summary")
                skip_total_row = loc.get("skip_total_row")
                
                # Return in the same format as Report.execute_script
                return [columns, result, message, chart, report_summary, skip_total_row]
                
        except Exception as e:
            # Log the error and re-raise it
            frappe.log_error(f"Report Extension Python Error: {str(e)}", "Report Extension")
            frappe.throw(f"Error executing Report Extension Python script: {str(e)}")
            return None
