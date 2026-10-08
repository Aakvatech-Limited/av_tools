# FULL ACCESS Role - Lead Implementor User Manual

## Purpose

The FULL ACCESS feature in AV Tools is a privileged implementation control. When enabled, AV Tools creates and continuously maintains a `FULL ACCESS` role across eligible non-Frappe DocTypes, Reports, Pages and Workspaces.

This feature is intentionally locked. Only the authorized Lead Implementor, signed in as the `Administrator` user, may enable or disable it.

## What the policy does

When enabled, AV Tools automatically grants the `FULL ACCESS` role to all eligible resources whose owning app is not `frappe`.

For DocTypes, the role receives Read, Write, Create, Delete, Select, Report, Export, Import, Share, Print and Email. Submit, Cancel and Amend are added only for submittable DocTypes.

For Reports, Pages and Workspaces, the role is added to their role access tables.

Frappe Framework-owned DocTypes, Reports, Pages and Workspaces are excluded. If stale FULL ACCESS entries exist on Frappe-owned resources, the synchronizer removes them.

## Who is allowed to enable it

Only the authorized Lead Implementor may perform this procedure.

The user must be signed in as:

`Administrator`

The server rejects attempts by every other user, even if the field is made visible or an API request is attempted.

## Why the setting is hidden and read-only

`AV Tools Settings.enable_full_access_role` ships with:

- Hidden = Yes
- Read Only = Yes
- Default = No

The field must be deliberately unlocked with Property Setters before it can be changed. This prevents accidental activation through normal configuration work.

## Enable FULL ACCESS

### 1. Sign in as Administrator

Do not use a normal System Manager or implementation user for this procedure.

### 2. Create or update the Hidden Property Setter

Open **Property Setter** and set:

- DocType: `AV Tools Settings`
- Field Name: `enable_full_access_role`
- Property: `hidden`
- Property Type: `Check`
- Value: `0`

Save.

### 3. Create or update the Read Only Property Setter

Create another Property Setter:

- DocType: `AV Tools Settings`
- Field Name: `enable_full_access_role`
- Property: `read_only`
- Property Type: `Check`
- Value: `0`

Save.

### 4. Reload AV Tools Settings

Open **AV Tools Settings** and reload the form.

The **Enable FULL ACCESS Role** checkbox should now be visible and editable.

If it is still hidden or read-only, do not attempt to bypass the control. Verify the Property Setters and clear cache if required.

### 5. Tick Enable FULL ACCESS Role

Tick the checkbox.

AV Tools immediately displays the **FULL ACCESS Authorization** consent dialog.

Read the warning carefully.

### 6. Click I Accept

Click **I Accept** only if you intend to enable the FULL ACCESS policy.

Acceptance does the following before the setting can be saved:

- verifies that the current user is exactly `Administrator`;
- verifies that the setting was deliberately unlocked;
- records the consent in **Activity Log**;
- records the current user and available request IP context;
- opens a short-lived authorization window for the settings save.

If the consent is not accepted, the server will reject enabling the feature.

### 7. Save AV Tools Settings

Save the document.

AV Tools then:

- creates the `FULL ACCESS` role if it does not already exist;
- synchronizes eligible DocTypes;
- synchronizes eligible Reports;
- synchronizes eligible Pages;
- synchronizes eligible Workspaces;
- removes stale FULL ACCESS access from Frappe Framework-owned resources;
- clears relevant caches.

### 8. Lock the field again

Immediately return the two Property Setters to their protected values:

**Hidden Property Setter**
- Value: `1`

**Read Only Property Setter**
- Value: `1`

Reload AV Tools Settings and verify that the setting is no longer visible/editable.

Do not leave the field unlocked after the procedure.

## Verify the audit trail

Open **Activity Log** and search for:

`FULL ACCESS consent accepted`

The record confirms that the privileged consent was accepted before activation.

The settings change itself is also traceable through normal Frappe document/version tracking where applicable.

## Verify the FULL ACCESS role

Open **Role** and confirm that `FULL ACCESS` exists.

Then spot-check representative business DocTypes, Reports, Pages and Workspaces.

Do not expect Frappe Framework-owned resources to contain FULL ACCESS. They are deliberately excluded.

## Automatic maintenance after activation

Once enabled, AV Tools continuously reconciles the policy.

It runs when:

- `bench migrate` completes;
- a new app is installed;
- a DocType is inserted or updated;
- a Report is inserted or updated;
- a Page is inserted or updated;
- a Workspace is inserted or updated.

This means a future installed app does not need to be manually added to an allow-list. Its eligible resources receive FULL ACCESS automatically unless they belong to the `frappe` app.

Likewise, new DocTypes introduced later by ERPNext, HRMS, AV Tools, client apps or other installed apps are automatically reconciled.

## Disabling FULL ACCESS management

Disabling the switch stops AV Tools from automatically maintaining the FULL ACCESS policy.

It does not automatically remove all permissions already granted. This is intentional to prevent an accidental checkbox change from causing a site-wide access outage.

Disabling the setting requires the same controlled procedure:

1. sign in as `Administrator`;
2. unlock the field with the two Property Setters;
3. change the setting;
4. save;
5. lock the field again.

Only the authorized Lead Implementor is permitted to perform this operation.

## Important security notes

- Do not assign the `Administrator` account to normal users.
- Do not leave the FULL ACCESS setting visible or editable after use.
- Do not bypass the consent endpoint with scripts or API calls.
- Do not manually grant FULL ACCESS to Frappe Framework-owned resources.
- FULL ACCESS is broad application access, but it does not deliberately bypass application-level `has_permission`, permission query conditions, workflows, User Permissions or server-side business validations.
- Review Error Log if synchronization reports a failure.

## Troubleshooting

### The checkbox does not appear

Confirm both Property Setters exist and are set to `0`, then reload the form.

### I Accept is rejected

Confirm:

- you are logged in as exactly `Administrator`;
- both Property Setters have successfully made the field visible and editable;
- the page was reloaded after creating the Property Setters.

### Saving says consent is required

The consent authorization is intentionally short-lived. Tick the field again, review the warning and click **I Accept**, then save promptly.

### A new app did not receive FULL ACCESS

Run `bench migrate` and review **Error Log**. The `after_app_install` hook should normally handle new installations immediately, while `after_migrate` acts as the authoritative reconciliation safety net.

### A Frappe Framework DocType has FULL ACCESS

Run a migration or trigger the FULL ACCESS synchronization. The policy removes stale FULL ACCESS permissions from Frappe-owned resources.

## Lead Implementor completion checklist

Before leaving the site:

- FULL ACCESS policy status is intentional.
- Consent was recorded in Activity Log.
- FULL ACCESS role exists when enabled.
- Representative non-Frappe business resources were verified.
- Frappe-owned resources were verified as excluded.
- Hidden Property Setter is restored to `1`.
- Read Only Property Setter is restored to `1`.
- AV Tools Settings field is no longer normally editable.
- Error Log contains no unresolved FULL ACCESS synchronization errors.
