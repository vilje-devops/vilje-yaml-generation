# Authenticating the workflow to Azure

Three supported methods. Never generate the credential itself, never ask for its value,
and never write it into a file.

**Which to recommend** is a team decision, held in one place: the *House auth default*
table in `questions.md`. Today that is **publish profile for App Service** (matching
Vilje's existing repos) and **OIDC for Container Apps** (publish profile cannot work
there). This file explains how each method works and what it costs; it does not decide
which one a new repo gets.

Security note, so the trade-off stays visible: OIDC is the strongest of the three. It
stores no credential at all, so there is nothing to leak and nothing to rotate. Publish
profile is chosen here for consistency and because it needs no Entra app registration -
not because it is safer. A team that can create app registrations should consider
standardising on OIDC instead.

## 1. OIDC federated credentials — recommended default

No secret is stored. GitHub mints a short-lived token per run and Entra ID trusts it for
one specific repo, branch or environment.

Workflow requirements (all three or it fails):

```yaml
permissions:
  id-token: write   # required to request the OIDC token
  contents: read

steps:
  - uses: azure/login@v3
    with:
      client-id: ${{ secrets.AZURE_CLIENT_ID }}
      tenant-id: ${{ secrets.AZURE_TENANT_ID }}
      subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
```

Repository secrets to create (these are identifiers, not passwords, but keep them as
secrets by convention):

| Secret | Holds |
|---|---|
| `AZURE_CLIENT_ID` | App registration (or user-assigned managed identity) client ID |
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Target subscription ID |

**The federated credential subject must match the workflow exactly.** This is the single
most common OIDC failure — put the exact string in the report:

| Trigger | Subject |
|---|---|
| Push to a branch | `repo:<owner>/<repo>:ref:refs/heads/<branch>` |
| A GitHub Environment | `repo:<owner>/<repo>:environment:<environment>` |
| Pull request | `repo:<owner>/<repo>:pull_request` |
| Tag push | `repo:<owner>/<repo>:ref:refs/tags/<tag>` |

If the workflow uses `environment: production`, the subject **must** be the `environment:`
form, not the `ref:` form. A branch-form subject on an environment-gated job fails with a
confusing `AADSTS700213`.

Manual prerequisites to list in the report (the developer does these, not you):

1. Create an app registration, note its client ID.
2. Add a federated credential of type "GitHub Actions deploying Azure resources" with the
   exact subject above.
3. Assign the app a role on the **resource group**, not the subscription — `Contributor`
   for App Service and Container Apps; `AcrPush` additionally when pushing to ACR.
4. Add the three repository secrets.

## 2. Service principal secret

A long-lived client secret stored as a GitHub secret. Works, expires, and leaks if the
repo is compromised. Use when OIDC is not permitted.

```yaml
- uses: azure/login@v3
  with:
    creds: ${{ secrets.AZURE_CREDENTIALS }}
```

`AZURE_CREDENTIALS` holds a JSON object with `clientId`, `clientSecret`, `subscriptionId`,
`tenantId`. **Never ask the user to paste it into chat.** Tell them to create it with
`az ad sp create-for-rbac --sdk-auth` and paste it directly into GitHub's secret field.

Note the expiry date in the report — an expired secret produces a deploy failure months
later that nobody connects to this setup.

`id-token: write` is **not** needed for this method.

## 3. Publish profile — App Service only

Simplest, weakest. The profile contains deployment credentials in plain XML.

```yaml
- uses: azure/webapps-deploy@v2
  with:
    app-name: {{AZURE_APP_NAME}}
    publish-profile: ${{ secrets.AZURE_WEBAPP_PUBLISH_PROFILE }}
```

No `azure/login` step. Does not work for Container Apps. The profile must be re-downloaded
and the secret updated whenever the app's publishing credentials are reset — call that out.

**`startup-command` is not supported with publish-profile auth.** The input exists on
`azure/webapps-deploy` but is ignored unless the action is authenticated through
`azure/login`. The startup command must instead be set once, by hand, in the Azure portal:

> Web App → **Configuration** → **General settings** → **Startup Command**

Examples to put there:

| Stack | Startup command |
|---|---|
| Next.js | `npm run start` |
| FastAPI / gunicorn | `gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000` |

Always say this explicitly in the report when the auth method is publish profile. A
generated workflow carrying `startup-command:` under a publish profile looks correct and
does nothing, which is the hardest kind of failure to diagnose.

## Compatibility matrix - check this before generating

| Target | OIDC | Service principal secret | Publish profile |
|---|---|---|---|
| App Service (code) | yes | yes | **yes** |
| App Service (container) | yes | yes | yes, but the registry push needs its own credentials |
| Container Apps | yes | yes | **NO - no such thing exists** |
| Static Web Apps | n/a | n/a | **NO** - SWA uses its own deployment token |

A publish profile is an App Service feature. Container Apps and Static Web Apps have no
publish profile at all, so the combination cannot be made to work - refuse it and offer
OIDC or a service principal secret. This is check `AZ-07`, and `validate_workflows.py`
fails on it.

Two further consequences of publish profile, both easy to miss:

- **The az CLI is not authenticated.** There is no `azure/login` step, so any `az ...` run
  step fails. That rules out the slot-swap step; deploy directly to the slot instead.
- **`id-token: write` must not be granted.** Nothing requests an OIDC token, so the
  permission is pure privilege with no purpose (SEC-03).

## Preserving an existing convention

If `detect_stack.py` reports `existing_auth_method`, that is the team established
convention. **Default to it.** Say which method you detected and that you are keeping it.

Switching a team to a different method is their decision, not yours - ask explicitly, and
never migrate silently. If `existing_auth_mixed` is true, different workflows disagree:
ask which to standardise on rather than picking one.

Also reuse the **existing secret names**. A repo using `AZURE_PUBLISH_PROFILE_PROD` should
not suddenly be handed a workflow referencing `AZURE_WEBAPP_PUBLISH_PROFILE` - that is a
silent failure the developer then has to debug.

## Choosing

| Situation | Use |
|---|---|
| New setup, team controls Entra | OIDC |
| Container Apps or any `az` CLI step | OIDC or SP secret (publish profile cannot do it) |
| Cannot create an app registration | Publish profile (App Service only) |
| Existing repo already using one of these | Keep it; note the trade-off, do not silently migrate |

## Rules

- Never generate, guess or echo a credential value.
- Never print a client ID, tenant ID or subscription ID you happened to find in the repo —
  if you find one committed in source, that is a `SEC-01` blocker.
- Always list the exact federated credential subject when OIDC is chosen. Mark the
  resource-side setup `Unknown` — you cannot verify Azure state.
