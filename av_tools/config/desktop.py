from frappe import _


def get_data():
    return [
        {
            "module_name": "AI Integration",
            "type": "module",
            "label": _("AI Integration"),
            "color": "blue",
            "icon": "octicon octicon-cpu",
        },
        {
            "module_name": "Weigh Bridge",
            "type": "module",
            "label": _("Weigh Bridge"),
            "color": "blue",
            "icon": "octicon octicon-file-directory",
        }
    ]
