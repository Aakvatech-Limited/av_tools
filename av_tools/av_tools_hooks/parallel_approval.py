import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import (
    create_custom_fields,
    delete_custom_fields,
)
from frappe import share as frappe_share


_APPROVER_TAB = "custom_av_approvers_tab"
_APPROVER_TABLE = "custom_av_approver_details"
_CACHE_KEY = "av_tools_approval_doctypes"


def _get_approval_doctypes() -> set:
    try:
        if getattr(frappe.flags, "in_migrate", False):
            return set()

        if not frappe.db.get_single_value("AV Tools Settings", "enable_multi_approval_document"):
            return set()

        if not frappe.db.table_exists("Approval Doctypes"):
            return set()

        rows = frappe.get_all(
            "Approval Doctypes",
            filters={"parenttype": "AV Tools Settings"},
            pluck="doctype_name",
        )
        return set(rows)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Parallel Approval: _get_approval_doctypes failed")
        return set()


def _should_process(doc) -> bool:
    if doc.doctype not in _get_approval_doctypes():
        return False
    if not getattr(doc, _APPROVER_TABLE, None):
        return False
    return True


def sync_approver_shares(doc, method=None):
    if doc.doctype not in _get_approval_doctypes():
        return

    # Query DB directly — more reliable than doc.custom_av_approver_details
    # which may be empty or stale depending on how the save was triggered.
    approver_rows = frappe.get_all(
        "Approver Details",
        filters={"parent": doc.name, "parenttype": doc.doctype},
        fields=["approver", "approver_name", "position", "delegate_to"],
    )

    desired = set()
    # Map user → display info for email notifications
    user_info = {}
    for row in approver_rows:
        if row.approver:
            desired.add(row.approver)
            user_info[row.approver] = {"name": row.approver_name or row.approver, "position": row.position or ""}
        if row.delegate_to:
            desired.add(row.delegate_to)
            if row.delegate_to not in user_info:
                delegate_name = frappe.get_cached_value("User", row.delegate_to, "full_name") or row.delegate_to
                user_info[row.delegate_to] = {"name": delegate_name, "position": row.position or ""}

    # Capture existing DocShare users BEFORE adding new ones to detect new additions
    existing = frappe.get_all(
        "DocShare",
        filters={"share_doctype": doc.doctype, "share_name": doc.name},
        fields=["user"],
    )
    existing_users = {s.user for s in existing if s.user}

    flags = {"ignore_share_permission": True}
    for user in desired:
        frappe_share.add_docshare(doc.doctype, doc.name, user, read=1, write=0, flags=flags)
        if user not in existing_users:
            _notify_approver_added(user, user_info.get(user, {}), doc)

    for share in existing:
        if share.user and share.user not in desired:
            frappe_share.remove(doc.doctype, doc.name, share.user, flags=flags)


def _notify_approver_added(user, info, doc):
    try:
        user_email = frappe.get_cached_value("User", user, "email") or user
        display_name = info.get("name") or user
        position = info.get("position") or ""

        site_url = frappe.utils.get_url()
        route = frappe.scrub(doc.doctype).replace("_", "-")
        doc_url = f"{site_url}/app/{route}/{doc.name}"

        added_by = frappe.get_cached_value("User", frappe.session.user, "full_name") or frappe.session.user

        subject = _("You have been added as an approver — {0} {1}").format(doc.doctype, doc.name)

        position_line = f"<p><b>{_('Position')}:</b> {frappe.utils.escape_html(position)}</p>" if position else ""

        message = f"""
<p>{_("Dear")} {frappe.utils.escape_html(display_name)},</p>
<p>{_("You have been assigned as an approver for the following document by")} <b>{frappe.utils.escape_html(added_by)}</b>:</p>
<table style="border-collapse:collapse;margin:12px 0;">
  <tr><td style="padding:4px 12px 4px 0;color:#555;">{_("Document Type")}</td><td><b>{frappe.utils.escape_html(doc.doctype)}</b></td></tr>
  <tr><td style="padding:4px 12px 4px 0;color:#555;">{_("Document")}</td><td><b>{frappe.utils.escape_html(doc.name)}</b></td></tr>
  {"<tr><td style='padding:4px 12px 4px 0;color:#555;'>" + _("Position") + "</td><td><b>" + frappe.utils.escape_html(position) + "</b></td></tr>" if position else ""}
</table>
<p>
  <a href="{doc_url}" style="background:#4563E9;color:#fff;padding:8px 18px;border-radius:4px;text-decoration:none;display:inline-block;">
    {_("Open Document")}
  </a>
</p>
<p style="color:#888;font-size:12px;">{_("Please review and approve or reject the document using the Approval button on the form.")}</p>
"""

        frappe.sendmail(
            recipients=[user_email],
            subject=subject,
            message=message,
            now=True,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Parallel Approval: approver email failed")


def block_submit_if_not_approved(doc, method=None):
    if getattr(frappe.flags, "in_migrate", False):
        return

    # Directly inspect the approver child table — no cache dependency.
    # The field only exists on doctypes configured for approval, so checking
    # its presence is a sufficient gate.
    approver_rows = getattr(doc, _APPROVER_TABLE, None)
    if not approver_rows:
        return

    rejected_by = []
    pending_by = []

    for row in approver_rows:
        name = row.approver_name or row.approver
        if row.rejected:
            rejected_by.append(name)
        elif not row.approved:
            pending_by.append(name)

    msgs = []
    if rejected_by:
        msgs.append(_("Document rejected by: {0}").format(", ".join(rejected_by)))
    if pending_by:
        msgs.append(_("Pending approval from: {0}").format(", ".join(pending_by)))

    if msgs:
        frappe.throw(title=_("Approval Pending"), msg="<br>".join(msgs))


def _field_defs(doctype: str) -> dict:
    meta = frappe.get_meta(doctype)
    our_fields = {_APPROVER_TAB, _APPROVER_TABLE}
    other_fields = [f for f in meta.fields if f.fieldname not in our_fields]
    last_field = other_fields[-1].fieldname if other_fields else None

    return {
        doctype: [
            {
                "fieldname": _APPROVER_TAB,
                "fieldtype": "Tab Break",
                "label": "Approvers",
                "insert_after": last_field,
            },
            {
                "fieldname": _APPROVER_TABLE,
                "fieldtype": "Table",
                "label": "Approver Details",
                "options": "Approver Details",
                "insert_after": _APPROVER_TAB,
            },
        ]
    }


def create_approval_fields(doctype: str) -> None:
    if not frappe.db.exists("DocType", doctype):
        frappe.log_error(
            f"Parallel Approval: DocType '{doctype}' does not exist — skipping field creation.",
            "Parallel Approval",
        )
        return
    create_custom_fields(_field_defs(doctype), update=True)


def delete_approval_fields(doctype: str) -> None:
    delete_custom_fields({doctype: [_APPROVER_TAB, _APPROVER_TABLE]})


def clear_approval_cache() -> None:
    pass  # Cache removed — _get_approval_doctypes queries DB directly


_QR_PRINT_FORMAT_HTML = """
{%- set pa_approvers = [] -%}
{%- for _r in (doc.custom_av_approver_details or []) -%}
  {%- if _r.approved -%}
    {%- set _sig = frappe.db.get_value("User", _r.approver, "custom_signature") -%}
    {%- set _ = pa_approvers.append({
        "full_name": _r.approver_name or _r.approver or "",
        "position": _r.position or "",
        "date": (_r.date | string)[:10] if _r.date else "",
        "signature": _sig or ""}) -%}
  {%- endif -%}
{%- endfor -%}
{% if pa_approvers %}
<table style="width:100%;border-collapse:collapse;margin-top:20px;">
  <thead>
    <tr>
      <th style="border:0.5px solid #888;padding:4px 6px;font-size:10px;text-align:center;">No.</th>
      <th style="border:0.5px solid #888;padding:4px 6px;font-size:10px;text-align:center;">Name and Position</th>
      <th style="border:0.5px solid #888;padding:4px 6px;font-size:10px;text-align:center;">Date</th>
      <th style="border:0.5px solid #888;padding:4px 6px;font-size:10px;text-align:center;width:220px;">Signature</th>
    </tr>
  </thead>
  <tbody>
    {% for ap in pa_approvers %}
    <tr>
      <td style="border:0.5px solid #888;padding:4px 6px;font-size:10px;text-align:center;vertical-align:middle;">{{ loop.index }}</td>
      <td style="border:0.5px solid #888;padding:4px 6px;font-size:10px;vertical-align:middle;">
        {{ ap.full_name }}<br><span style="color:#555;">{{ ap.position }}</span>
      </td>
      <td style="border:0.5px solid #888;padding:4px 6px;font-size:10px;vertical-align:middle;">{{ ap.date }}</td>
      <td style="border:0.5px solid #888;padding:4px 6px;height:90px;vertical-align:middle;">
        {% if ap.date and ap.signature %}
          <img src="{{ ap.signature }}" style="max-height:80px;max-width:220px;object-fit:contain;">
        {% else %}
          {%- set _qr_url = frappe.utils.get_url() ~ '/app/' ~ (doc.doctype | lower | replace(' ', '-')) ~ '/' ~ doc.name -%}
          <img src="{{ generate_reviewer_qr(ap.full_name ~ ' | ' ~ ap.position ~ ' | ' ~ _qr_url) }}" style="max-height:80px;max-width:80px;object-fit:contain;">
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}
"""


_QR_FIELD_NAME = "_av_approver_qr"


def _get_doctype_print_formats(doctype: str) -> list:
    return frappe.get_all(
        "Print Format",
        filters={"doc_type": doctype},
        fields=["name", "custom_format", "html", "format_data"],
    )


def create_approver_qr_print_format(doctype: str) -> None:
    import json

    formats = _get_doctype_print_formats(doctype)
    if not formats:
        return

    for pf_data in formats:
        pf = frappe.get_doc("Print Format", pf_data["name"])

        if pf.custom_format and pf.html:
            # Full custom Jinja HTML — append with markers if not already present
            marker = "<!-- av_tools_reviewer_qr -->"
            if marker in pf.html:
                continue
            pf.html = pf.html.rstrip() + "\n\n" + marker + "\n" + _QR_PRINT_FORMAT_HTML
            pf.save(ignore_permissions=True)
        else:
            # Standard / Jinja format using format_data — add an HTML entry at the end
            try:
                fd = json.loads(pf.format_data or "[]")
            except Exception:
                continue
            if any(f.get("fieldname") == _QR_FIELD_NAME for f in fd):
                continue
            fd.append({
                "fieldname": _QR_FIELD_NAME,
                "fieldtype": "HTML",
                "label": "Approver QR Codes",
                "print_hide": 0,
                "options": _QR_PRINT_FORMAT_HTML,
            })
            pf.format_data = json.dumps(fd)
            pf.save(ignore_permissions=True)

    frappe.db.commit()


def delete_approver_qr_print_format(doctype: str) -> None:
    import json
    import re

    for pf_data in _get_doctype_print_formats(doctype):
        pf = frappe.get_doc("Print Format", pf_data["name"])

        if pf.custom_format and pf.html:
            marker = "<!-- av_tools_reviewer_qr -->"
            if marker not in pf.html:
                continue
            pf.html = re.sub(
                re.escape(marker) + r".*",
                "",
                pf.html,
                flags=re.DOTALL,
            ).rstrip()
            pf.save(ignore_permissions=True)
        else:
            try:
                fd = json.loads(pf.format_data or "[]")
            except Exception:
                continue
            cleaned = [f for f in fd if f.get("fieldname") != _QR_FIELD_NAME]
            if len(cleaned) == len(fd):
                continue
            pf.format_data = json.dumps(cleaned)
            pf.save(ignore_permissions=True)

    frappe.db.commit()


def boot_session(bootinfo):
    try:
        bootinfo.parallel_approval_doctypes = list(_get_approval_doctypes())
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Parallel Approval: boot_session failed")
        bootinfo.parallel_approval_doctypes = []


@frappe.whitelist()
def get_approval_doctypes_for_js():
    return list(_get_approval_doctypes())


@frappe.whitelist()
def submit_approval_action(doctype, docname, action, reason=None):
    if action not in ("approve", "reject", "clear_rejection"):
        frappe.throw(_("Invalid action"))

    doc = frappe.get_doc(doctype, docname)
    current_user = frappe.session.user

    approver_row = None
    for row in (getattr(doc, _APPROVER_TABLE, None) or []):
        if row.approver == current_user or row.delegate_to == current_user:
            approver_row = row
            break

    if not approver_row:
        frappe.throw(_("You are not listed as an approver for this document."))

    is_expired = approver_row.expiry_date and frappe.utils.getdate(approver_row.expiry_date) < frappe.utils.getdate(frappe.utils.nowdate())
    if is_expired and current_user == approver_row.approver and approver_row.delegate_to:
        frappe.throw(_(
            "Your approval authority for this document expired on {0}. "
            "This has been escalated to {1}."
        ).format(frappe.utils.formatdate(approver_row.expiry_date), approver_row.delegate_to))

    acting_name = frappe.get_cached_value("User", current_user, "full_name") or current_user

    acting_as_delegate = current_user == approver_row.delegate_to and current_user != approver_row.approver
    if acting_as_delegate:
        approver_name = frappe.get_cached_value("User", approver_row.approver, "full_name") or approver_row.approver
        delegate_suffix = _(" (as delegate for {0})").format(approver_name)
    else:
        delegate_suffix = ""

    if action == "approve":
        updates = {"approved": 1, "rejected": 0, "rejection_reason": "", "date": frappe.utils.now()}
        comment_html = _("<b>{0}</b> reviewed and approved this document{1}.").format(acting_name, delegate_suffix)

    elif action == "reject":
        if not reason:
            frappe.throw(_("A rejection reason is required."))
        safe_reason = frappe.utils.escape_html(reason)
        updates = {"approved": 0, "rejected": 1, "rejection_reason": reason, "date": frappe.utils.now()}
        comment_html = _(
            "<b>{0}</b> rejected this document{1}.<br><b>Reason:</b> {2}"
        ).format(acting_name, delegate_suffix, safe_reason)

    else:  # clear_rejection
        updates = {"approved": 0, "rejected": 0, "rejection_reason": "", "date": frappe.utils.now()}
        comment_html = _("<b>{0}</b> cleared their rejection{1}.").format(acting_name, delegate_suffix)

    frappe.db.set_value("Approver Details", approver_row.name, updates)

    frappe.get_doc({
        "doctype": "Comment",
        "comment_type": "Comment",
        "reference_doctype": doctype,
        "reference_name": docname,
        "comment_email": current_user,
        "comment_by": acting_name,
        "content": comment_html,
    }).insert(ignore_permissions=True)

    return True
