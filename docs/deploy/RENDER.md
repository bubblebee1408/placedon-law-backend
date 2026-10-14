# Deploy the gateway on Render

The durable replacement for the laptop tunnel. This hosts the **/v2 gateway**
(`gateway/app.py`, `create_app()`) on Render with a managed Postgres, so the live site talks
to a real backend instead of an ephemeral `trycloudflare` URL.

Blueprint: [`render.yaml`](../../render.yaml) at the repo root. This runbook is the operator
side — the parts an agent cannot do (connect your account, pay, choose a region, seed the first
tenant, copy the key to the frontend).

> **State of play.** Case-law search (`sources.search` / `research.cases`) is merged to `main`
> on both backend and frontend. It needs **no model key** — discovery reads the committed index
> and judgments stream from keyless public S3. So the minimum live deploy is just **Postgres +
> the three gateway vars**. Add a model later to turn `ask` back on (last section).

---

## What the blueprint sets

| | Value | Why |
|---|---|---|
| Runtime | Python 3.12.7 (`PYTHON_VERSION`) | matches local |
| Build | `pip install -r requirements-gateway.txt` | gateway deps: fastapi, uvicorn, `psycopg[binary]`, azure-\*, boto3 |
| Start | `uvicorn gateway.app:create_app --factory --host 0.0.0.0 --port $PORT` | `create_app()` self-configures from env |
| Health | `GET /v1/health` (no key) | liveness without a credential |
| Pre-deploy | `python scripts/migrate.py --url "$PLACEDON_DATABASE_URL"` | apply migrations before traffic switches |
| DB | managed Postgres, `basic-256mb`, region `frankfurt` | RLS is the reason for Postgres (see `requirements-gateway.txt`) |

**Cost / plan.** `starter` web (~always-on) + `basic-256mb` Postgres are small paid plans.
You can set both to `free` to trial, but: free Postgres **expires in ~30 days and is wiped**,
free web **spins down when idle** (cold start on first hit) and **skips `preDeployCommand`** —
so on free you must run the migration by hand (step 4b). Free is not "durable"; for retiring
the tunnel, keep the paid plans.

---

## Steps

### 1. Connect the repo
In the Render dashboard → **New → Blueprint** → connect `bubblebee1408/placedon-law-backend`
→ select the `main` branch. Render reads `render.yaml` and proposes the web service + database.
Do **not** click create until step 3 (you'll want the secrets ready).

### 2. Generate the service key
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
Keep this value. It is both `PLACEDON_GATEWAY_SERVICE_KEY` (backend) and the frontend's
`PLACEDON_GATEWAY_KEY` — they **must match**. It is never sent to a browser.

### 3. Choose the tenant + actor UUIDs
```bash
python -c "import uuid; print('tenant', uuid.uuid4()); print('actor ', uuid.uuid4())"
```
These become `PLACEDON_GATEWAY_TENANT_ID` and `PLACEDON_GATEWAY_ACTOR_ID`. All three gateway
vars must be set **together** — partial config fails startup on purpose. Set them as
`sync: false` env vars in the dashboard, then create the Blueprint.

### 4. First deploy
Render runs build → `preDeployCommand` (migrations) → start. Watch the deploy log:
- migrations apply cleanly, **or**
- `migrate.py` prints `REFUSED: connected as … a superuser`. That means your DB role is a
  superuser and RLS would be bypassed. Render managed DBs are normally non-super owners; if you
  hit this, use the non-super role Render provisions, don't grant superuser.

**4b. On the `free` plan only** (no preDeploy): open the web service → **Shell** and run
`python scripts/migrate.py --url "$PLACEDON_DATABASE_URL"` once after the first deploy, and
again after any deploy that adds a migration.

### 5. Seed the first tenant + actor
The service key acts as the tenant/actor from step 3; those rows must exist before the engine
can write (FK constraints). Case-law *search* reads the committed index and works without them,
but seed anyway so `matters`, runs, and audit work. From the web service **Shell**:
```bash
psql "$PLACEDON_DATABASE_URL" <<SQL
insert into tenants (tenant_id, name) values ('<TENANT_UUID>', 'Placedon')
  on conflict do nothing;
insert into actors (actor_id, tenant_id, role, label)
  values ('<ACTOR_UUID>', '<TENANT_UUID>', 'lawyer', 'deployment')
  on conflict do nothing;
SQL
```
> Verify the exact `tenants` / `actors` columns against `gateway/migrations/001_core.sql` and
> `018_users_roles.sql` before running — this is the one step tied to the live schema, and the
> column list there wins over this snippet.

### 6. Verify the backend is up
```bash
curl -s https://<your-service>.onrender.com/v1/health          # 200, no key
curl -s https://<your-service>.onrender.com/v2/sources/search \
  -H "Authorization: Bearer <SERVICE_KEY>" \
  -H 'Content-Type: application/json' \
  -d '{"query":"Tata Sons Cyrus Mistry"}'
# -> JSON with a `judgments` array; expect a 2021 Tata/Cyrus Supreme Court hit, tier LICENSED
```

### 7. Re-point the frontend (this is what retires the tunnel)
In the frontend project (Vercel `placedon-legal`), set the **server-only** vars to the Render
service and redeploy:
- `GATEWAY_URL` / `PLACEDON_API_ORIGIN` → `https://<your-service>.onrender.com`
- `PLACEDON_GATEWAY_KEY` → the step-2 service key
- drop the dead `NEXT_PUBLIC_API_BASE_URL` `trycloudflare` value

Then `pnpm dlx vercel --prod` from the frontend deploy worktree and confirm the live
`placedon.com` "Case law" surface returns the Tata/Cyrus judgment.

---

## Turning `ask` back on (optional, later)
Case-law search needs no model. The statutory `ask`/audit path does. The client-data provider
is **Claude on Amazon Bedrock** (ap-south-1) per `PLAN_22`; the Azure path is the non-client
engine. Add the relevant provider credentials as `sync: false` env vars when you want `ask` to
answer — until then it abstains honestly rather than failing.

## Reversal
Nothing here is one-way. Delete the Blueprint, drop the Render Postgres, and point the frontend
back — the repo is unchanged and no legal data lives on Render that isn't reproducible from the
corpus and migrations.
