# Deployment readiness rubric

Apply every applicable check. Skip a whole section only when it does not apply (for
example skip `DOCK-*` when there is no Dockerfile and the target is not container-based)
and say in the report that you skipped it and why.

**Severity**

| Level | Meaning |
|---|---|
| `blocker` | The deployment will fail, or a secret will leak. Must be fixed before the first deploy. |
| `warning` | Deploy will probably work, but the app will be fragile, insecure or hard to operate. |
| `info` | Good practice. Mention once; do not pad the report with these. |

**Labels** — every finding carries one:

- `Verified` — you read the file or ran the command and observed the result.
- `Assumed` — inferred from convention, not directly observed. State the inference.
- `Unknown` — needs user input or Azure/GitHub access you do not have.

---

## BUILD — build reproducibility

| ID | Sev | Check | Fix |
|---|---|---|---|
| BUILD-01 | blocker | A lockfile is committed (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `poetry.lock`, `uv.lock`, `requirements.txt` pinned, `packages.lock.json`) | Commit the lockfile. Without it CI installs different versions than the developer tested. |
| BUILD-02 | blocker | A single deterministic build command exists and is discoverable (`npm run build`, `dotnet publish`, `pip install -r`, Makefile target) | Add a `build` script. CI cannot guess. |
| BUILD-03 | blocker | Runtime version is pinned — in repo files (`.nvmrc`, `engines.node`, `global.json`, `.python-version`, Dockerfile base tag) **or** in a workflow `env:` block (`NODE_VERSION`, `PYTHON_VERSION`). The detector reports the latter as `runtime_pins_in_workflow`. | Pin it somewhere. Do **not** report this as missing when a workflow already pins it — that is a false blocker. |
| BUILD-04 | warning | Pinned runtime version is still supported by the chosen Azure target | Check the target's supported runtime list; upgrade if the version is retired. |
| BUILD-05 | warning | Build output path is stable and known (`dist/`, `build/`, `.next/`, `publish/`) | Needed for the artifact upload step. |
| BUILD-06 | warning | Build does not require network access to a private registry without a configured token | Add the registry auth step, or vendor the dependency. |
| BUILD-07 | info | `.gitignore` excludes build output and `node_modules` | |
| BUILD-08 | blocker | An existing install command that carries an explanatory comment is preserved verbatim | The detector reports `install_commands[].has_rationale`. A comment above `npm install` usually documents a real platform workaround (optional deps resolving differently on Linux). Replacing it with the conventional `npm ci` breaks the build. Never "correct" a documented choice — ask. |

## RUN — runtime contract with Azure

| ID | Sev | Check | Fix |
|---|---|---|---|
| RUN-01 | blocker | The server binds the port from the environment, not a hardcoded literal. App Service and Container Apps inject `PORT`; a hardcoded `3000`/`8000` returns 502. | Use `process.env.PORT ?? 3000` / `os.environ.get("PORT", 8000)` / `ASPNETCORE_URLS`. |
| RUN-02 | blocker | The server binds `0.0.0.0`, not `127.0.0.1`/`localhost` | Bind all interfaces or the platform cannot reach the container. |
| RUN-03 | blocker | A start command exists and is discoverable (`npm start`, `gunicorn`/`uvicorn` entry, `dotnet <dll>`, Dockerfile `CMD`) | Define one; App Service otherwise guesses and usually guesses wrong. |
| RUN-04 | warning | A health endpoint exists (`/health`, `/healthz`, `/api/health`) | Add one. Container Apps probes need it; App Service health check uses it for instance recycling. |
| RUN-05 | warning | Application logs to stdout/stderr, not only to a local file | File logs are lost on restart and invisible in Log Stream / Application Insights. |
| RUN-06 | warning | `SIGTERM` is handled for graceful shutdown | Without it, in-flight requests are dropped on every deploy and scale-in. |
| RUN-07 | warning | Startup completes inside the platform timeout (App Service default 230s; Container Apps probe budget) | Move slow work out of startup path. |
| RUN-08 | info | No reliance on local disk for state that must persist | App Service `/home` persists; container filesystems do not. |

## ENV — configuration

| ID | Sev | Check | Fix |
|---|---|---|---|
| ENV-01 | blocker | Every environment variable the code reads is accounted for — present in `.env.example`, documented, or flagged as needing an App Setting | Enumerate from source. A missing variable is the single most common first-deploy failure. |
| ENV-02 | blocker | No `.env` containing real values is committed to git | `git rm --cached .env`, add to `.gitignore`, **and rotate everything it held** — git history keeps it. |
| ENV-03 | warning | `.env.example` exists and lists every key with a dummy value | It becomes the checklist for App Settings. |
| ENV-04 | warning | Config is read at startup with clear failure, not silently defaulted to a dev value | Fail fast on missing required config; a silent localhost DB fallback in production is worse than a crash. |
| ENV-05 | warning | Frontend build-time variables are distinguished from backend runtime variables | `VITE_*`/`NEXT_PUBLIC_*` are baked into the bundle at build time and are **public**. They must be build args, and must never hold a secret. |

## SEC — secrets and supply chain

| ID | Sev | Check | Fix |
|---|---|---|---|
| SEC-01 | blocker | No hardcoded credential, connection string, API key, private key or token in source | Move to GitHub secrets / Key Vault and **rotate the exposed value**. Report file and line only — never the value. |
| SEC-02 | blocker | Generated workflows reference secrets only as `${{ secrets.NAME }}` | Never inline. |
| SEC-03 | blocker | Workflow `permissions:` is least-privilege, not the default write-all | Set `contents: read` at workflow level and add only what each job needs. |
| SEC-04 | blocker | No `pull_request_target` combined with checkout of the PR head | That combination executes untrusted code with repository secrets in scope. |
| SEC-05 | warning | Third-party actions are pinned to a release tag (or better, a commit SHA), never `@main` | A moving ref is remote code execution in your pipeline on someone else's schedule. |
| SEC-06 | warning | Secrets are not passed to steps that echo, log or upload them | Check `env:` blocks on `run:` steps that print. |
| SEC-07 | warning | Deployment credentials are scoped to one resource group, not the whole subscription | Narrow the role assignment scope. |
| SEC-08 | info | Dependency scanning enabled (Dependabot / `npm audit` / `pip-audit`) | |

## DOCK — container image (only when containerized)

| ID | Sev | Check | Fix |
|---|---|---|---|
| DOCK-01 | blocker | `Dockerfile` exists at a known build context path | Required for Container Apps and container-based App Service. |
| DOCK-02 | blocker | `EXPOSE` / `CMD` port agrees with what the app actually binds and with the target's ingress port | A mismatch is a silent 502. |
| DOCK-03 | warning | `.dockerignore` exists and excludes `node_modules`, `.git`, `.env` | Without it the build context leaks files and is slow. `.env` copied into an image is a leak. |
| DOCK-04 | warning | Multi-stage build; final stage has no build toolchain | |
| DOCK-05 | warning | Runs as a non-root `USER` | |
| DOCK-06 | warning | Base image is a pinned tag or digest, not `:latest` | |
| DOCK-07 | info | Image architecture matches the target (`linux/amd64` unless ARM is configured) | Cross-arch builds from Apple Silicon fail at runtime on amd64 hosts. |

## DATA — database and migrations

| ID | Sev | Check | Fix |
|---|---|---|---|
| DATA-01 | blocker | If migrations exist, the deploy path defines when and where they run | Unmanaged migrations cause an outage on the first deploy. Decide: pre-deploy job, release step, or manual. |
| DATA-02 | blocker | Connection string comes from config, never from source | See SEC-01. |
| DATA-03 | warning | Migrations are safe to re-run and safe to run concurrently across instances | Multi-instance deploys run the step more than once. |
| DATA-04 | warning | Network path from the Azure target to the database is possible (firewall rule, VNet, private endpoint) | Azure SQL / Postgres flexible server block outbound by default. **Unknown without Azure access — flag it.** |
| DATA-05 | info | A rollback path exists for a failed migration | |

## CI — workflow structure

| ID | Sev | Check | Fix |
|---|---|---|---|
| CI-01 | blocker | Workflow YAML parses and has `on:`, `jobs:`, and `runs-on:` per job | |
| CI-02 | blocker | Deploy triggers on the intended branch only — not on every push or every PR | |
| CI-03 | warning | Build and test run before deploy; deploy `needs:` the build job | Otherwise a broken build ships. |
| CI-04 | warning | The artifact deployed is the artifact that was tested — not a second, separate build | Build once, upload, deploy that artifact. |
| CI-05 | warning | Dependency cache configured (`actions/setup-node` `cache:`, `setup-python` `cache:`) | |
| CI-06 | warning | Production deploy is gated by a GitHub Environment with required reviewers | |
| CI-07 | warning | `concurrency:` set so two pushes cannot deploy simultaneously | Concurrent deploys to one slot produce an indeterminate result. |
| CI-08 | info | `timeout-minutes` set on jobs | |
| CI-10 | warning | CI and deploy workflows do not both trigger on the same event | If `ci.yml` and `deploy.yml` both run on push to the release branch, every merge builds twice. Keep CI on `pull_request` and deploy on `push`, or have deploy `needs:` the CI job. |
| CI-09 | warning | When a repo holds more than one deploying workflow, each has an `on.push.paths:` filter | Without it every push deploys every service — a CSS change redeploys the backend. The detector reports `deploy_workflow_count` and `deploy_workflows_without_paths`. |

## AZ — Azure target fit

| ID | Sev | Check | Fix |
|---|---|---|---|
| AZ-01 | blocker | The chosen Azure service can actually host this app shape | See `azure-targets.md`. A stateful websocket app on Static Web Apps will not work. |
| AZ-02 | blocker | Auth method is decided and its prerequisites are listed | See `auth.md`. |
| AZ-07 | blocker | Auth method is compatible with the chosen target - publish profile is App Service only | Container Apps and Static Web Apps have no publish profile. Switch to OIDC or a service principal secret. |
| AZ-08 | blocker | Publish-profile workflows contain no `az ...` step and no `id-token: write` | A publish profile does not authenticate the az CLI and requests no OIDC token. |
| AZ-09 | warning | An existing auth convention is preserved, or the change was explicitly agreed | Switching a team auth method silently causes a failure they cannot explain. |
| AZ-03 | `Unknown` | Target resource already exists, with the right SKU and runtime stack | You cannot verify this. Always report as Unknown and list it as a manual prerequisite. |
| AZ-04 | `Unknown` | The deploying identity holds the required role on the resource | Same — always Unknown. |
| AZ-05 | warning | For container targets, a registry (ACR or GHCR) is chosen and its auth is configured | |
| AZ-06 | warning | Region and resource naming follow team convention | Ask; never invent a name. |

## OPS — operability

| ID | Sev | Check | Fix |
|---|---|---|---|
| OPS-01 | warning | A rollback path exists — deployment slot swap, previous revision, or redeploy of the prior tag | Decide before the first deploy, not during the first incident. |
| OPS-02 | warning | Deploy verification step (health probe against the deployed URL) | Without it the workflow reports green on a broken deploy. |
| OPS-03 | warning | App Service: staging slot used with swap, rather than deploying straight to production | |
| OPS-04 | info | Monitoring/alerting configured (Application Insights) | |
| OPS-05 | info | `DEPLOYMENT.md` kept current | This skill writes it. |

---

## Scoring

Do not produce a single numeric score — it hides blockers behind a reassuring number.
Report counts per severity plus an explicit verdict:

- **Blocked** — one or more open blockers. List them.
- **Ready with caveats** — no blockers; warnings remain. List them.
- **Cannot determine** — a fact required for a verdict is Unknown. Name it.
