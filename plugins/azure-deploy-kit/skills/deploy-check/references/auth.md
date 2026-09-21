# Authenticating the workflow to Azure

Three supported methods. Default to OIDC. Never generate the credential itself, never ask
for its value, and never write it into a file.

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
