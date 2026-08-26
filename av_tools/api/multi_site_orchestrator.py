import frappe
import requests
from frappe import _


@frappe.whitelist()
def disable_user_on_all_sites(email, site_configuration_name):
    """
    Disable user across all enabled sites using standard Frappe REST API.
    No custom app needed on client sites.
    """
    if not email:
        frappe.throw(_("Email is required"))
    
    if not site_configuration_name:
        frappe.throw(_("Site Configuration name is required"))
    
    site_config = frappe.get_doc("Site Configuration", site_configuration_name)
    
    if not site_config.sites:
        frappe.throw(_("No sites configured"))
    
    results = []
    
    for site_entry in site_config.sites:
        if not site_entry.enabled:
            results.append({
                "site_name": site_entry.site_name,
                "site_url": site_entry.site_url,
                "status": "skipped",
                "message": "Site disabled in configuration"
            })
            continue
        
        result = _disable_user_on_site(
            email=email,
            site_name=site_entry.site_name,
            site_url=site_entry.site_url,
            api_key=site_entry.api_key,
            api_secret=site_entry.get_password("api_secret")
        )
        results.append(result)
    
    return {
        "email": email,
        "configuration": site_configuration_name,
        "action": "disable",
        "total_sites": len(site_config.sites),
        "enabled_sites": len([s for s in site_config.sites if s.enabled]),
        "results": results
    }


@frappe.whitelist()
def enable_user_on_all_sites(email, site_configuration_name):
    """
    Enable user across all enabled sites using standard Frappe REST API.
    No custom app needed on client sites.
    """
    if not email:
        frappe.throw(_("Email is required"))
    
    if not site_configuration_name:
        frappe.throw(_("Site Configuration name is required"))
    
    site_config = frappe.get_doc("Site Configuration", site_configuration_name)
    
    if not site_config.sites:
        frappe.throw(_("No sites configured"))
    
    results = []
    
    for site_entry in site_config.sites:
        if not site_entry.enabled:
            results.append({
                "site_name": site_entry.site_name,
                "site_url": site_entry.site_url,
                "status": "skipped",
                "message": "Site disabled in configuration"
            })
            continue
        
        result = _enable_user_on_site(
            email=email,
            site_name=site_entry.site_name,
            site_url=site_entry.site_url,
            api_key=site_entry.api_key,
            api_secret=site_entry.get_password("api_secret")
        )
        results.append(result)
    
    return {
        "email": email,
        "configuration": site_configuration_name,
        "action": "enable",
        "total_sites": len(site_config.sites),
        "enabled_sites": len([s for s in site_config.sites if s.enabled]),
        "results": results
    }


def _disable_user_on_site(email, site_name, site_url, api_key, api_secret):
    """
    Disable user using standard Frappe REST API.
    Client site only needs API key/secret - no app installation.
    """
    try:
        if not site_url.startswith(("http://", "https://")):
            site_url = f"https://{site_url}"
        
        site_url = site_url.rstrip("/")
        
        # Standard Frappe REST API endpoint
        endpoint = f"{site_url}/api/resource/User/{email}"
        
        response = requests.put(
            endpoint,
            headers={
                "Authorization": f"token {api_key}:{api_secret}",
                "Content-Type": "application/json"
            },
            json={"enabled": 0},
            timeout=30
        )
        
        if response.status_code == 200:
            return {
                "site_name": site_name,
                "site_url": site_url,
                "status": "success",
                "message": f"User {email} disabled successfully"
            }
        elif response.status_code == 404:
            return {
                "site_name": site_name,
                "site_url": site_url,
                "status": "success",
                "message": f"User {email} does not exist on this site"
            }
        elif response.status_code == 403:
            return {
                "site_name": site_name,
                "site_url": site_url,
                "status": "error",
                "message": "Permission denied - check API user permissions"
            }
        elif response.status_code == 401:
            return {
                "site_name": site_name,
                "site_url": site_url,
                "status": "error",
                "message": "Authentication failed - check API credentials"
            }
        else:
            return {
                "site_name": site_name,
                "site_url": site_url,
                "status": "error",
                "message": f"HTTP {response.status_code}: {response.text[:200]}"
            }
            
    except requests.exceptions.Timeout:
        return {
            "site_name": site_name,
            "site_url": site_url,
            "status": "error",
            "message": "Timeout after 30 seconds"
        }
    except requests.exceptions.ConnectionError:
        return {
            "site_name": site_name,
            "site_url": site_url,
            "status": "error",
            "message": "Connection failed - check URL"
        }
    except Exception as e:
        frappe.log_error(
            title=f"Multi-site user disable error: {site_name}",
            message=f"Site: {site_url}\nEmail: {email}\nError: {str(e)}"
        )
        return {
            "site_name": site_name,
            "site_url": site_url,
            "status": "error",
            "message": f"Exception: {str(e)}"
        }


def _enable_user_on_site(email, site_name, site_url, api_key, api_secret):
    """
    Enable user using standard Frappe REST API.
    Client site only needs API key/secret - no app installation.
    """
    try:
        if not site_url.startswith(("http://", "https://")):
            site_url = f"https://{site_url}"
        
        site_url = site_url.rstrip("/")
        
        # Standard Frappe REST API endpoint
        endpoint = f"{site_url}/api/resource/User/{email}"
        
        response = requests.put(
            endpoint,
            headers={
                "Authorization": f"token {api_key}:{api_secret}",
                "Content-Type": "application/json"
            },
            json={"enabled": 1},
            timeout=30
        )
        
        if response.status_code == 200:
            return {
                "site_name": site_name,
                "site_url": site_url,
                "status": "success",
                "message": f"User {email} enabled successfully"
            }
        elif response.status_code == 404:
            return {
                "site_name": site_name,
                "site_url": site_url,
                "status": "success",
                "message": f"User {email} does not exist on this site"
            }
        elif response.status_code == 403:
            return {
                "site_name": site_name,
                "site_url": site_url,
                "status": "error",
                "message": "Permission denied - check API user permissions"
            }
        elif response.status_code == 401:
            return {
                "site_name": site_name,
                "site_url": site_url,
                "status": "error",
                "message": "Authentication failed - check API credentials"
            }
        else:
            return {
                "site_name": site_name,
                "site_url": site_url,
                "status": "error",
                "message": f"HTTP {response.status_code}: {response.text[:200]}"
            }
            
    except requests.exceptions.Timeout:
        return {
            "site_name": site_name,
            "site_url": site_url,
            "status": "error",
            "message": "Timeout after 30 seconds"
        }
    except requests.exceptions.ConnectionError:
        return {
            "site_name": site_name,
            "site_url": site_url,
            "status": "error",
            "message": "Connection failed - check URL"
        }
    except Exception as e:
        frappe.log_error(
            title=f"Multi-site user enable error: {site_name}",
            message=f"Site: {site_url}\nEmail: {email}\nError: {str(e)}"
        )
        return {
            "site_name": site_name,
            "site_url": site_url,
            "status": "error",
            "message": f"Exception: {str(e)}"
        }

@frappe.whitelist()
def update_site_configuration(doc):
    """
    Update an existing Site Configuration document, including the child table.
    """
    doc = frappe._dict(doc)
    
    existing_doc = frappe.get_doc("Site Configuration", doc.name)
    existing_doc.title = doc.title
    existing_doc.description = doc.description
    
    # Clear existing sites and add new ones
    existing_doc.sites = []
    for site_entry in doc.sites:
        existing_doc.append("sites", site_entry)
        
    existing_doc.save(ignore_permissions=True)
    
    return existing_doc


