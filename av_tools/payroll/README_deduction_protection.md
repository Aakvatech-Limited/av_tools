# Payroll Deduction Protection & Recovery (HRMS v16)

**Status:** Experimental, disabled by default. Requires integration testing before production rollout.

## Configuration
1. Run `bench --site <site> migrate` after installing the AV Tools branch.
2. Open **Payroll Deduction Protection Policy** and create one record for the company.
3. Select gross pay or a basic salary component as the protected earnings basis.
4. Set Protected Earnings Percentage (for example 33.333333%) and optional absolute minimum.
5. Add **only explicitly authorized, non-statutory** Salary Components to Recoverable Deductions, with numeric priority (lower numbers first).
6. Enable the policy after testing a sample payroll.

**No nationwide Tanzanian private-sector two-thirds limit is asserted by this feature.** The example percentage is configurable and must be validated against the applicable employment contract, employer category and legal requirements.

## Behavior
- Frappe HRMS computes gross, PAYE, statutory items and Lending instalments normally.
- AV Tools checks remaining earnings against the protected floor. If mandatory deductions already violate the protection, the Salary Slip fails validation/submission with an exception; no statutory or loan instalment is silently altered.
- Approved recoverable Salary Components are allocated in priority order; current-month scheduled amounts before older outstanding arrears (FIFO).
- Deferred balances are recorded on Salary Slip submission in **Payroll Deduction Recovery Entry**, linked to employee, company and salary component.
- Later Salary Slips can recover previous balances, preserving the original deferred entry link.
- Cancellations reverse the recovery entries on the associated Salary Slip. To reverse an original deferred entry, later Salary Slips that recovered it must be cancelled first.
- Draft previews do not write recovery entries, and the original salary structure is not mutated.

## Boundaries
- **Not** a replacement for loan repayment, employee advance, or statutory accounting ledgers.
- No automatic tax, NSSF, HESLB, court-order, garnishment, or Lending-managed loan deferral.
- Mixed-currency employee obligations are not supported: policy is company-local and Salary Slips must be checked for currency consistency before deployment.
- Protection applies to payable-period gross or selected basic-salary earning, not an assumed normal monthly salary.
- No ledger entries are journalled separately: the deferred amount is an uncollected deduction obligation, *not automatically a booked financial liability*.
- Recovery allocations must undergo concurrent-payroll and cancellation integration tests before enabling this feature.

## Validation checklist before merge
- Validate standard Salary Slip, Payroll Entry batch generation, repeated preview and salary re-computation.
- Test pay-period with zero gross, statutory-only payroll, variable tax, and multiple voluntary deduction rows.
- Test carried balances across several months, full recovery and partial recovery.
- Test Salary Slip cancellation with and without downstream recoveries; stale recovery plans; concurrent payroll submissions.
- Confirm salary accounts and employee net pay, statutory reporting, loan reconciliation, multi-company isolation.
- Review legally protected earnings basis and per-component recovery authorization.
