### Av Tools

Av Tools

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app av_tools
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/av_tools
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### Selling Pricing Engine (v16)

Optional company-based pricing with fixed Item/Warehouse overrides, cost calculations, fallback generation, reviewed publication, sales retrieval and five operating reports. Disabled until configured.

See the [Phase 1 setup, user guide and validation checklist](av_tools/selling_pricing_engine/README.md).

### Bank transactions from GL and statement report (v16)

Open **Bank Transaction** and choose **Generate from GL Entries**. Select a company,
one bank account (or all accessible company bank accounts), an optional From Date
and a mandatory inclusive Cut-off Date. **Preview Only** defaults to enabled.
The background run lists each eligible, skipped and created record. Clear Preview
Only to create one draft per individual GL Entry, including split voucher rows.

Each draft retains its source GL Entry, source voucher and generation run. An
existing active source GL link prevents a duplicate. An existing voucher link
without GL identification reserves that voucher on the same bank GL account,
including draft reservations. Tagged sibling GL rows remain separately eligible.
Cancelled/discarded transactions release their active source key. No transactions
are submitted by generation; standard allocation and voucher clearance occur when
the drafts are submitted. GL-derived transactions represent book history, so use
actual bank statements for independent reconciliation.

**Bank Transaction Statement** offers Transaction Detail with running balance and
Monthly Summary with opening balance, deposits, withdrawals and closing balance.
It includes submitted transactions only. Opening balances use earlier imported
transactions and depend on complete history. Relative periods resolve on the
server whenever the report runs.

Both features use only the standard **System Manager**, **Accounts Manager** and
**Accounts User** roles, plus existing document/company permissions. No custom
roles are created. See the [migration and validation notes](docs/bank_transaction_tools.md).

### License

mit
