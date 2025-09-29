import frappe
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
                return self.execute_custom_python_script(av_report_extension_doc.script_python, filters)
        
        # Fall back to original script report execution
        return super().execute_script_report(filters)
    
    def execute_custom_python_script(self, script_python, filters):
        """Execute custom Python script like a standard report module"""
        try:
            import sys

            # Create a single namespace that acts like a real module
            # This is the key fix - all functions must be in the same namespace
            module_namespace = {
                '__builtins__': __builtins__,
                '__name__': f'report_extension_{frappe.scrub(self.name)}',
                '__file__': f'<report_extension_{frappe.scrub(self.name)}>',
                '__package__': None,
            }

            # Add all of sys.modules so imports work exactly like in standard reports
            module_namespace.update(sys.modules)

            # Execute the script with the same dict for globals AND locals
            # This ensures all function definitions are in the same namespace
            # and can call each other (just like a real Python module)
            exec(script_python, module_namespace, module_namespace)

            # Now call the execute function like a standard report
            if 'execute' in module_namespace:
                # Call the execute function with filters (like execute_module does)
                result = module_namespace['execute'](frappe._dict(filters) if filters else frappe._dict())
                return result
            else:
                # Fallback: check if data was set (script report style)
                if module_namespace.get("data"):
                    return module_namespace["data"]
                else:
                    # Return individual components
                    columns = module_namespace.get("columns", [])
                    result = module_namespace.get("result", [])
                    message = module_namespace.get("message")
                    chart = module_namespace.get("chart")
                    report_summary = module_namespace.get("report_summary")
                    skip_total_row = module_namespace.get("skip_total_row")

                    return [columns, result, message, chart, report_summary, skip_total_row]

        except Exception as e:
            # Log the error with more details for debugging
            error_msg = str(e)
            if "is not defined" in error_msg:
                # Provide helpful guidance for missing function errors
                missing_func = error_msg.split("'")[1] if "'" in error_msg else "unknown"
                helpful_msg = f"Missing function '{missing_func}'. Make sure to copy the ENTIRE General Ledger file content (all functions), not just the execute() function."
                frappe.throw(f"Report Extension Error: {helpful_msg}")
            else:
                frappe.throw(f"Error executing Report Extension Python script: {error_msg}")
            return None
