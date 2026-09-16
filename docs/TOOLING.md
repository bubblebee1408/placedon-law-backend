# Tooling — cloud CLIs and MCP servers

Written 2026-09-14 (overnight loop, task E2). What is installed on the development
Mac, what is **not** configured, and the exact commands to add AWS, Azure and Kaggle
MCP servers once the founder supplies credentials and approves.

**Nothing below has been registered or given credentials.** Each command is quoted
from the vendor's own page on the date above; a claim without one is marked.

---

## 1. CLIs on this machine

| CLI | Version | Credentials | Note |
|---|---|---|---|
| AWS CLI | aws-cli/2.36.44 | none | `brew install awscli` |
| Oracle OCI CLI | 3.92.1 | none | `brew install oci-cli` |
| Azure CLI | 2.90.0 | **signed in** as the Azure for Students account | used to create `placedon-law-eval` (UAE North) |
| Google Cloud SDK | 584.0.0 | none | Vertex route built in `checker/gemini_model.py`, not yet used |
| GitHub CLI | 2.90.0 | existing login | |
| Kaggle CLI | 2.2.4 | none | **not on PATH** — installed at `~/Library/Python/3.12/bin/kaggle`. Add that directory to PATH, or call it by full path |

MCP runtimes present: `uvx` (uv 0.11.7), `npx` and Node v22.19.0. **Absent:** `dotnet`,
`docker` — so the Azure server's `dnx` and container routes are unavailable here.

## 2. MCP servers registered today

From `claude mcp list` on 2026-09-14: claude.ai Canva (connected), claude-mem (connected),
Vercel (needs authentication), 21st (connected), reddit (connected), `magic` (failed:
API key missing). **No AWS, Azure or Kaggle server is registered.**

---

## 3. AWS

Source: [awslabs/mcp README](https://github.com/awslabs/mcp), read 2026-09-14.

| Server | Command (from the README) | What it touches |
|---|---|---|
| AWS Knowledge / documentation | `uvx awslabs.aws-documentation-mcp-server@latest` | AWS public documentation only |
| AWS MCP Server (**preview**, managed by AWS) | `uvx mcp-proxy-for-aws@latest https://aws-mcp.us-east-1.api.aws/mcp` | Your AWS account, via IAM; CloudTrail-logged |

Authentication (README): `AWS_PROFILE` and `AWS_REGION` environment variables.
The README names an **Agent Toolkit for AWS** as the successor to these servers.

To add to Claude Code (the `claude mcp add <name> -e KEY=value -- <command>` form is Claude
Code's own syntax; the command after `--` is the README's):

```
claude mcp add aws-docs -- uvx awslabs.aws-documentation-mcp-server@latest
claude mcp add aws -e AWS_PROFILE=<profile> -e AWS_REGION=ap-south-1 -- \
  uvx mcp-proxy-for-aws@latest https://aws-mcp.us-east-1.api.aws/mcp
```

**Before adding the managed server:** its endpoint is in **us-east-1**. Anything an agent
sends through it leaves India. It must never carry a client document or a quoted span
(CLAUDE.md; PLAN_07). The documentation server carries no account or client data and is
the safe one to add first.

## 4. Azure

Sources: [Microsoft Learn — Get started with the Azure MCP Server](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/get-started)
(updated 2026-08-27) and the [Azure.Mcp.Server README](https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/README.md), read 2026-09-14.

Packages: npm `@azure/mcp`, NuGet `Azure.Mcp`, PyPI `msmcp-azure`.

| Route | Command (from the README) | Works here? |
|---|---|---|
| npx | `npx -y @azure/mcp@latest server start` | yes |
| uvx | `uvx --from msmcp-azure azmcp server start` | yes |
| dnx | `dnx Azure.Mcp -- azmcp server start` | no — `dotnet` absent |

Authentication (README): the Azure Identity SDK — `az login`, or `DefaultAzureCredential`
with `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`.

**Telemetry is on by default** and goes to Microsoft; the README says use of the software
is consent. Disable it explicitly:

```
claude mcp add azure -e AZURE_MCP_COLLECT_TELEMETRY=false -- \
  npx -y @azure/mcp@latest server start
```

**No read-only mode is documented** on the README. Signed in as today's account, an agent
using this server could change or create resources on the Azure for Students subscription
— which the overnight loop's own rules forbid. Decide tool scope before registering it.

## 5. Kaggle

An official Kaggle MCP server exists: [Kaggle blog — Kaggle's Official MCP Server](https://www.kaggle.com/blog/kaggles-official-mcp-server)
and [Kaggle docs — MCP Server](https://www.kaggle.com/docs/mcp).

**Neither Kaggle page could be read on 2026-09-14** — both render with JavaScript and
return an empty shell to a non-browser fetch. What is known comes from a third party:

| Fact | Status | Source |
|---|---|---|
| Remote server at `https://www.kaggle.com/mcp`, no local install | **Reported, not confirmed by Kaggle** | a user's config in [openai/codex issue #23627](https://github.com/openai/codex/issues/23627), 20 May 2026 — the server initialised |
| Authentication is OAuth | **Reported, not confirmed by Kaggle** | same issue: Kaggle's OAuth rejected Codex's short `client_id` ("ClientId too small: codex"); no Kaggle staff reply |

If the docs page confirms it in a browser, Claude Code's standard form for a remote HTTP
server would be (untested here; the OAuth login would complete through `/mcp`):

```
claude mcp add --transport http kaggle https://www.kaggle.com/mcp
```

Community servers (`54yyyu/kaggle-mcp`, `Dishant27/kaggle-MCP`, `Galaxy-Dawn/kaggle-mcp` and
others) appear in search results. They are **not** Kaggle's, they take an API key rather than
OAuth, and they are not recommended here.

The Kaggle CLI itself authenticates with an API token (`kaggle.json`); none is configured.

---

## 6. Rules for adding any of these

1. The founder supplies credentials and approves each server. Keys go in the environment or
   `.env` (git-ignored), never in chat, never in a committed file.
2. **No client document, and no span quoted from one, goes to an MCP server** — least of all
   one whose endpoint is outside India (§3).
3. Prefer read-only scopes. Where a server has none (§4), use an identity whose permissions
   are read-only.
4. Disable vendor telemetry where the server allows it (§4).
5. Re-check commands against the vendor page before use. Package names and preview endpoints
   move; every one above was read on 2026-09-14.
