# Template conventions

These files are **filled in, not rewritten**. Read the template, substitute tokens, delete
the conditional blocks that do not apply, and write the result. Do not author workflow
YAML from memory — that is what makes output inconsistent between runs.

## Two distinct brace syntaxes

| Syntax | Belongs to | You must |
|---|---|---|
| `{{TOKEN}}` | this template system | replace before writing |
| `${{ github.ref }}` | GitHub Actions expressions | **leave exactly as-is** |

Never substitute anything inside `${{ ... }}`. Getting these confused produces a workflow
that fails at runtime with an unhelpful error.

Tokens are written quoted (`node-version: "{{NODE_VERSION}}"`) so the template files are
themselves valid YAML and can be parse-tested. Keep the quotes when a value is a version
number, a branch name, or anything YAML would otherwise coerce (`3.10` becomes a float,
`on`/`yes`/`no` become booleans).

## Conditional blocks

Written as comments so the raw template still parses:

```yaml
# {{#if TESTS}}
      - name: Test
        run: "{{TEST_COMMAND}}"
# {{/if}}
```

Keep the block and drop the two marker comment lines when the condition holds. Delete the
whole block including markers when it does not. Never leave a `{{#if}}` marker in output.

## Token reference

### Common

| Token | Source | Example |
|---|---|---|
| `{{DEFAULT_BRANCH}}` | git | `main` |
| `{{APP_PATH}}` | detector / user | `.` or `services/api` |
| `{{CONCURRENCY_GROUP}}` | derived | `deploy-api-production` |
| `{{ENVIRONMENT_NAME}}` | user | `production` |

### Node

| Token | Source | Example |
|---|---|---|
| `{{NODE_VERSION}}` | `.nvmrc`, `engines.node` | `22` |
| `{{PACKAGE_MANAGER}}` | lockfile | `npm` / `pnpm` / `yarn` |
| `{{LOCKFILE_PATH}}` | detector | `package-lock.json` |
| `{{INSTALL_COMMAND}}` | package manager | `npm ci` |
| `{{BUILD_COMMAND}}` | `package.json` scripts | `npm run build` |
| `{{TEST_COMMAND}}` | `package.json` scripts | `npm test` |
| `{{LINT_COMMAND}}` | `package.json` scripts | `npm run lint` |
| `{{BUILD_OUTPUT_PATH}}` | framework convention | `dist` |

### Python

| Token | Example |
|---|---|
| `{{PYTHON_VERSION}}` | `3.12` |
| `{{INSTALL_COMMAND}}` | `pip install -r requirements.txt` |
| `{{TEST_COMMAND}}` | `pytest` |

### .NET

| Token | Example |
|---|---|
| `{{DOTNET_VERSION}}` | `9.0.x` |
| `{{PROJECT_PATH}}` | `src/Api/Api.csproj` |

### Authentication

Exactly one auth method applies per generated workflow. `{{AUTH_METHOD}}` is the recorded
choice; the templates branch on the three `{{#if AUTH_*}}` blocks.

| Token / flag | Meaning |
|---|---|
| `{{AUTH_METHOD}}` | `oidc` / `service_principal_secret` / `publish_profile` |
| `{{#if AUTH_OIDC}}` | keep for OIDC federated credentials (default) |
| `{{#if AUTH_SP_SECRET}}` | keep for a service principal secret |
| `{{#if AUTH_PUBLISH_PROFILE}}` | keep for a publish profile - **App Service only** |

**Secret names are not tokens.** The templates carry the conventional names below. If the
repository already uses different ones, the detector reports them as
`workflow_auth[].secret_names` and `publish_profile_secret` - use the repo names and list
them in the report.

| Method | Secrets referenced | `id-token: write` |
|---|---|---|
| OIDC | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | **required** |
| Service principal secret | `AZURE_CREDENTIALS` | must be absent |
| Publish profile | `AZURE_WEBAPP_PUBLISH_PROFILE` | must be absent |

Substitution rules, in order:

1. Keep one `AUTH_*` block, delete the other two **including their marker comments**.
2. For OIDC keep `id-token: write`; for the other two **delete that line**. Granting it
   unused is privilege with no purpose, and `validate_workflows.py` fails on it.
3. Publish profile gives no `azure/login`, so the az CLI is unauthenticated in that job:
   - delete the `{{#if SLOT_SWAP}}` block and every `az ...` run step
   - for containers use `REGISTRY_ACR_ADMIN` or `REGISTRY_GHCR`, never `REGISTRY_ACR_CLI`
4. Publish profile with Container Apps or Static Web Apps is invalid - refuse (AZ-07).

### Registry flags (container targets)

| Flag | When |
|---|---|
| `{{#if REGISTRY_ACR_CLI}}` | ACR via `az acr login` - needs OIDC or SP secret |
| `{{#if REGISTRY_ACR_ADMIN}}` | ACR via admin user - the only ACR option under publish profile |
| `{{#if REGISTRY_GHCR}}` | ghcr.io via `GITHUB_TOKEN` - works with any auth method |

### Azure

| Token | Ask the user — never invent | Example |
|---|---|---|
| `{{AZURE_APP_NAME}}` | yes | `vilje-api-prod` |
| `{{AZURE_RESOURCE_GROUP}}` | yes | `rg-vilje-prod-weu` |
| `{{AZURE_SLOT_NAME}}` | yes | `staging` |
| `{{AZURE_CONTAINER_APP_NAME}}` | yes | `ca-vilje-api` |
| `{{AZURE_CONTAINER_APP_ENV}}` | yes | `cae-vilje-prod` |
| `{{REGISTRY_SERVER}}` | yes | `viljeacr.azurecr.io` or `ghcr.io` |
| `{{IMAGE_NAME}}` | derive from repo, confirm | `vilje/api` |
| `{{TARGET_PORT}}` | detector, confirm | `8000` |
| `{{DOCKERFILE_PATH}}` | detector | `./Dockerfile` |
| `{{BUILD_CONTEXT}}` | detector | `.` |

## Rules

1. **Every token gets substituted or becomes a visible TODO.** Never ship a bare
   `{{TOKEN}}` without a `# TODO(you):` comment directly above explaining what goes there.
2. **Action versions come from `../references/versions.md`**, not from the template if the
   two ever disagree.
3. **Delete what does not apply.** A repo with no lint script gets no lint step. An empty
   step that echoes "no tests configured" is noise.
4. **Secrets are `${{ secrets.NAME }}` only.** No exceptions.
5. **Keep `permissions:` minimal.** `contents: read` at workflow level; add `id-token: write`
   only on the job that calls `azure/login` with OIDC.
6. After writing, run the validator. A template that was filled wrong usually fails to
   parse, which is the cheapest possible place to catch it.

## Adding a new target

1. Add `deploy-<target>.yml` here, with tokens following these conventions.
2. Add a row to the decision table and the template table in
   `../references/azure-targets.md`.
3. Add any new action to `../references/versions.md`.
4. Test it once against a real repo before committing. An untested template is worse than
   no template, because it looks authoritative.
