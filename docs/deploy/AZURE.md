# Deploy to Azure from GitHub Actions

Production: resource group `placedon-prod` — App Service `placedon-api-hyd` (Linux, Python
3.12, Hyderabad) and Postgres Flexible `placedon-pg-uae` (UAE North, database `placedon`).
The workflow is [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml). It
replaces the laptop runbook and does the same steps in the same order.

## Deploying

Actions → **deploy** → **Run workflow** on `main`. A reviewer of the `production`
environment approves, then the job:

1. Refuses by name if any secret below is missing, or if the run is not on `main`.
2. Builds a zip of the git checkout (with `.git`, no GitHub token: the engine refuses to
   answer unless `git rev-parse HEAD` names its commit) plus
   [`ops/azure/startup.sh`](../../ops/azure/startup.sh) at the root.
3. Logs in to Azure by OIDC (no stored Azure password).
4. Opens a Postgres firewall rule for **this runner's IP only**, named
   `gha-deploy-<run id>-<attempt>`.
5. `scripts/migrate.py --plan`, then `--apply`: a `pg_dump` backup as the admin role first
   (`--backup-url`), then the pending migrations as `placedon_app`. `migrate.py` refuses a
   superuser, a missing or unreadable backup, and an edited already-applied migration.
6. Optionally copies the backup to Blob (see below).
7. Deletes the firewall rule. This step runs even when an earlier step failed, and fails
   the run loudly if the rule is still there afterwards.
8. `az webapp deploy --type zip`.
9. Polls `/v1/health` for up to 15 minutes until `checker_commit` is the deployed commit,
   then fails unless the store is `postgres`, files are `azure-blob` and a queue is present.

Never change App Service settings while a deploy runs: Azure restarts and cancels it.
Only one deploy runs at a time, and a running one is never cancelled.

## One-time setup (the owner)

### 1. An Azure identity the workflow can log in as

```bash
SUB=$(az account show --query id -o tsv)
APP_ID=$(az ad app create --display-name placedon-github-deploy --query appId -o tsv)
az ad sp create --id "$APP_ID"
# Trust GitHub's token for this repository's `production` environment, and nothing else.
az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "github-production",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:bubblebee1408/placedon-law-backend:environment:production",
  "audiences": ["api://AzureADTokenExchange"]
}'
# What it may touch: the production resource group only.
az role assignment create --assignee "$APP_ID" --role Contributor \
  --scope "/subscriptions/$SUB/resourceGroups/placedon-prod"
```

Contributor on the resource group is the simple choice. Narrower, if wanted: *Website
Contributor* on the web app plus a custom role with
`Microsoft.DBforPostgreSQL/flexibleServers/firewallRules/*` on the Postgres server.

If the repository moves or is renamed, the federated credential's `subject` must change
with it, or the login step fails.

### 2. The `production` environment

GitHub → Settings → Environments → **New environment** `production`:

- **Required reviewers**: the people who may approve a production deploy.
- **Deployment branches**: `main` only.
- Add the secrets below **as environment secrets** (not repository secrets), so a job
  sees them only after a reviewer approves.

Create the environment **before** the first run: a workflow that names an environment
which does not exist makes an unprotected one. (The secrets check still stops that run.)

### 3. Secrets (environment `production`)

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | `$APP_ID` from step 1 |
| `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| `AZURE_SUBSCRIPTION_ID` | `$SUB` from step 1 |
| `PG_ADMIN_USER` | the Postgres admin login (used only for the backup) |
| `PG_ADMIN_PASSWORD` | its password |
| `PG_APP_PASSWORD` | the `placedon_app` password (migrations run as this role) |

The workflow names them only as `${{ secrets.X }}`; no value is in the repository.

### 4. Optional: keep each backup

The runner is thrown away after the job, and the `pg_dump` with it. The backup still has a
job (`migrate.py` refuses to migrate without a readable one), and Azure's own automatic
backups (point-in-time restore, 7 days by default) are the restore path. To keep every
pre-migration dump as well, set repository **variables** `BACKUP_STORAGE_ACCOUNT` (and
optionally `BACKUP_CONTAINER`, default `db-backups`), create that private container, and
grant the identity *Storage Blob Data Contributor* on it. The dumps hold client data:
never use a public container, and never upload them as a GitHub artifact.

### 5. First run checks

- The App Service startup command must still run `startup.sh` from the bundle root (as
  today). The script now serves `ops.asgi:app`, the same code as the old `azure_asgi.py`.
- `SCM_DO_BUILD_DURING_DEPLOYMENT=false` stays set (Azure's build step drops `.git`).

## Why a temporary firewall rule

Postgres admits only the web app's outbound addresses. A GitHub-hosted runner has a
different public IP on every run, from a range too large to allow-list safely. Options
considered:

| Option | Verdict |
|---|---|
| Temporary rule for the runner's single IP, removed in an always-run step | **Implemented.** Open for minutes, one address, named per run |
| Allow all of GitHub's published Actions ranges | Rejected: thousands of addresses shared with every GitHub user |
| "Allow Azure services" on the server | Rejected: admits any Azure tenant's traffic |
| Run migrations from inside the App Service (startup or SSH) | Possible later; couples migrations to app boot and loses the backup-first gate |
| Self-hosted runner or VNet + private endpoint | The durable answer; costs a VM or a network redesign |

If a run dies so hard that the cleanup step never runs (a cancelled runner), list leftover
rules with `az postgres flexible-server firewall-rule list -g placedon-prod --server-name
placedon-pg-uae -o table` and delete any `gha-deploy-*`.
