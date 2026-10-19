# FULL ACCESS Role - Lead Implementor User Manual

## Purpose

The FULL ACCESS feature in AV Tools is a privileged implementation control. When enabled, AV Tools creates and continuously maintains a `FULL ACCESS` role across eligible non-Frappe DocTypes, Reports, Pages and Workspaces.

Configuration is maintained in **Full Access Role Setup**, with one setup record per Company.

> Important: the setup record is company-specific for governance and audit. Frappe Role permissions themselves are site-wide. Enabling FULL ACCESS for any Company activates the FULL ACCESS policy for eligible resources across the site. Company/User Permissions continue to control company-level data access.

## What the policy does

When at least one **Full Access Role Setup** is enabled, AV Tools automatically grants the `FULL ACCESS` role to eligible resources whose owning app is not `frappe`.

For DocTypes, the role receives Read, Write, Create, Delete, Select, Report, Export, Import, Share, Print and Email. Submit, Cancel and Amend are added only for submittable DocTypes.

For Reports, Pages and Workspaces, the role is added to their role access tables.

### Frappe Framework exclusion

AV Tools must never create FULL ACCESS `Custom DocPerm` records for DocTypes owned by the `frappe` app.

Ownership is resolved using the DocType module and `frappe.get_module_app()`.

During reconciliation:

- Frappe-owned DocTypes are skipped for grant creation.
- Any stale FULL ACCESS `Custom DocPerm` found on a Frappe-owned DocType is removed.
- Non-Frappe DocTypes remain eligible.

This exclusion is also enforced inside the permission creation function as a second safety check.

## Who is allowed to enable it

Only the authorized Lead Implementor may perform this procedure.

The user must be signed in as:

`Administrator`

All other users are rejected server-side when attempting to enable FULL ACCESS or accept the consent.

## Create the company setup

1. Sign in as `Administrator`.
2. Open **Full Access Role Setup**.
3. Create a new record.
4. Select the Company.
5. Leave **Enable FULL ACCESS Role** unticked.
6. Save the setup.

There can be one setup record per Company.

The setup must be saved before FULL ACCESS can be enabled so the consent can be linked to a permanent auditable record.

## Enable FULL ACCESS

### 1. Open the saved company setup

Open the required **Full Access Role Setup** record.

### 2. Tick Enable FULL ACCESS Role

Tick **Enable FULL ACCESS Role**.

AV Tools immediately resets the checkbox and displays the **FULL ACCESS Authorization** dialog.

### 3. Review the warning

The warning explains that:

- the setup is recorded against the selected Company;
- the FULL ACCESS role itself is site-wide;
- broad access will be granted to eligible non-Frappe DocTypes, Reports, Pages and Workspaces;
- only the authorized Lead Implementor using `Administrator` may proceed;
- consent will be recorded in Activity Log.

### 4. Click I Accept

Click **I Accept** only if you intend to activate the policy.

Acceptance:

- verifies that the current user is exactly `Administrator`;
- confirms that the setup record already exists;
- writes the consent to **Activity Log**;
- records the Company and setup reference;
- records the current user and available request IP context;
- opens a short-lived authorization window for the save.

### 5. Save the setup

After consent succeeds, the checkbox is set to enabled. Save the document.

AV Tools then:

- creates the `FULL ACCESS` role if required;
- synchronizes eligible DocTypes;
- synchronizes eligible Reports;
- synchronizes eligible Pages;
- synchronizes eligible Workspaces;
- removes stale FULL ACCESS permissions from Frappe Framework-owned resources;
- clears relevant caches.

The setup record also stores the latest consent user and consent datetime.

## Verify the audit trail

Open **Activity Log** and search for:

`FULL ACCESS consent accepted - <Company>`

The record links back to **Full Access Role Setup**.

Verify:

- User = `Administrator`
- Reference DocType = `Full Access Role Setup`
- Reference Name = the Company setup
- Company appears in the consent content
- request IP is present when available

## Verify the FULL ACCESS role

Open **Role** and confirm that `FULL ACCESS` exists.

Then spot-check:

- an ERPNext business DocType;
- an AV Tools DocType;
- a custom/client app DocType;
- a non-Frappe Report;
- a non-Frappe Page;
- a non-Frappe Workspace.

Also spot-check one Frappe Framework DocType and confirm that no FULL ACCESS `Custom DocPerm` exists for it.

## New apps and new DocTypes

Once the policy is active, AV Tools automatically reconciles after:

- `bench migrate`;
- installation of a new app;
- creation/update of a DocType;
- creation/update of a Report;
- creation/update of a Page;
- creation/update of a Workspace.

New apps do not require an allow-list.

If a new DocType belongs to the `frappe` app, it remains excluded.

If a new DocType belongs to ERPNext, HRMS, AV Tools or another non-Frappe app, it is eligible for FULL ACCESS.

## Multiple Companies

Each Company may have its own **Full Access Role Setup** record for governance and implementation tracking.

However, because Frappe role permissions are site-wide:

- if **any** company setup has FULL ACCESS enabled, the site-wide FULL ACCESS policy remains active;
- disabling one Company setup does not stop the policy if another Company setup remains enabled;
- Company/User Permissions remain responsible for restricting data by Company.

Do not interpret the setup as creating company-specific Role Permission Manager rules.

## Disabling FULL ACCESS management

To stop automatic FULL ACCESS synchronization:

1. sign in as `Administrator`;
2. open each enabled **Full Access Role Setup**;
3. untick **Enable FULL ACCESS Role**;
4. save.

When no setup records remain enabled, AV Tools stops maintaining the policy.

Disabling management does **not** automatically remove permissions already granted. This avoids accidental site-wide loss of access.

If complete permission removal is required, perform a separately reviewed cleanup procedure.

## Important security notes

- Only `Administrator` may enable/disable this configuration.
- Do not assign the Administrator account to normal users.
- Do not manually create FULL ACCESS Custom DocPerm records on Frappe-owned DocTypes.
- FULL ACCESS does not deliberately bypass application-level `has_permission`, permission query conditions, workflows, User Permissions or server-side business validations.
- Review Error Log if synchronization reports failures.
- Remember that the configuration record is company-scoped but the Role permission effect is site-wide.

## Troubleshooting

### I cannot create or change the setup

Confirm you are signed in as exactly `Administrator`.

### I Accept is rejected

Confirm:

- you are signed in as `Administrator`;
- the Full Access Role Setup has already been saved;
- the record still exists.

### Saving says consent is required

The consent authorization is intentionally short-lived. Tick the field again, review the warning, click **I Accept**, then save promptly.

### A new app did not receive FULL ACCESS

Confirm at least one **Full Access Role Setup** is enabled.

Then run `bench migrate` and review **Error Log**.

### A Frappe Framework DocType has FULL ACCESS

Run synchronization or `bench migrate`.

The policy removes stale FULL ACCESS permissions from Frappe-owned DocTypes and never creates new ones there.

## Lead Implementor completion checklist

Before leaving the site:

- Full Access Role Setup exists for the intended Company.
- The site-wide effect of FULL ACCESS has been understood.
- Consent was recorded in Activity Log.
- Latest consent user/date are recorded on the setup.
- FULL ACCESS role exists when enabled.
- Representative non-Frappe resources were verified.
- Frappe-owned DocTypes were verified as having no FULL ACCESS Custom DocPerm.
- All Company/User Permissions remain appropriate.
- Error Log contains no unresolved FULL ACCESS synchronization errors.
