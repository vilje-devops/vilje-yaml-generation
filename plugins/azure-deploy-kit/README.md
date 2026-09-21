# azure-deploy-kit

Analyzes an application repository and generates application-specific GitHub Actions CI/CD
YAML for Azure. **Generates files only — it never deploys.**

Install and usage: see the [repository README](../../README.md).

---

## How it works

Three layers, deliberately separated:

1. **`scripts/detect_stack.py`** — deterministic facts. Walks the repo and emits JSON:
   languages, frameworks, package managers, lockfiles, build/test/start commands, pinned
   runtime versions, listening ports, environment variable names, Dockerfiles, IaC files,
   existing workflows, and the locations of suspected hardcoded secrets. Same repo in,
   same facts out, every run.

2. **`skills/deploy-check/SKILL.md` + `references/`** — judgement. The model applies the
   rubric to the facts, asks only what the repo cannot answer, and selects templates.

3. **`templates/`** — the YAML itself. Generation is token substitution plus pruning, not
   free authoring. This is what keeps output consistent between runs and between repos.

If the model ever wrote workflow YAML from memory instead of from a template, the
consistency guarantee is gone. That separation is the point of the design.

---

## Authentication

Three methods, branched inside the templates with `{{#if AUTH_*}}` blocks rather than
duplicated into separate files:

| Block | Method | Valid for |
|---|---|---|
| `AUTH_OIDC` | federated credentials, no stored secret | App Service, Container Apps |
| `AUTH_SP_SECRET` | `AZURE_CREDENTIALS` JSON | App Service, Container Apps |
| `AUTH_PUBLISH_PROFILE` | `AZURE_WEBAPP_PUBLISH_PROFILE` | **App Service only** |

Three consequences of publish profile that the generator must handle, all enforced by
`validate_workflows.py`:

1. No `azure/login`, so the **az CLI is unauthenticated** - no slot swap, no `az acr login`.
2. **`id-token: write` must be absent** - nothing requests an OIDC token.
3. **Container Apps and Static Web Apps reject it outright** - they have no publish profile.

`detect_stack.py` reports `existing_auth_method` so the skill preserves a team convention
instead of switching it. See `skills/deploy-check/references/auth.md`.

## The generated report

`DEPLOYMENT.md` is filled from `skills/deploy-check/templates/DEPLOYMENT.template.md`, the
same way workflows are filled from their templates - a report written freehand comes out
different every run.

It answers five questions, as its five sections:

1. What did the skill create?
2. How does the deployment work?
3. What do I need to configure?
4. How do I run the deployment?
5. How do I know whether it succeeded?

Written for three readers at once: the developer debugging the first failure, the team lead
deciding whether to adopt it, and someone non-technical following what happens.

`skills/deploy-check/examples/DEPLOYMENT.example.md` is a complete worked example, built
from real detector and validator output on the `publish-profile-app-service` fixture.

After writing a report the skill runs:

```bash
python skills/deploy-check/scripts/validate_report.py DEPLOYMENT.md
```

which enforces: the five sections exist, the disclaimer is verbatim, no secret value leaked
in, no token was left unfilled, evidence labels are used, and the report never claims a
deployment succeeded.

## Tests

```bash
python tests/run_tests.py -v
```

98 assertions across the detector, the validator, the templates, the report template, the
report linter, a no-inline-credential safety sweep, and a regression group built from the
Vilje team's real workflows. See `tests/README.md`.

### Configuration that lives in the workflow

Reading only repo files produces false blockers. `detect_stack.py` also parses each
workflow's `env:` block, its `${{ vars.X }}` references, its resolved Azure app name, and
whether an install step carries an explanatory comment. A runtime pinned as
`NODE_VERSION: "22.x"` in a workflow is pinned - reporting it as missing is a bug, and
test group 8 keeps it from coming back.

## Maintenance

### Refresh action versions (quarterly)

`references/versions.md` is the single source of truth. Templates must never reference a
version that is not listed there.

```bash
for r in actions/checkout actions/setup-node actions/setup-python actions/setup-dotnet \
         actions/upload-artifact actions/download-artifact Azure/login Azure/webapps-deploy \
         Azure/static-web-apps-deploy Azure/container-apps-deploy-action \
         docker/build-push-action docker/login-action; do
  printf "%-40s " "$r"
  curl -s "https://api.github.com/repos/$r/releases/latest" | grep '"tag_name"' | cut -d'"' -f4
done
```

Update `versions.md` and the templates together, and move the "Last verified" date.

Note `actions/upload-artifact` and `actions/download-artifact` version independently.
Always pin both to the same major — a mismatched pair fails at runtime.

### Add an Azure target

1. Add `templates/deploy-<target>.yml` following `templates/TEMPLATES.md`.
2. Add rows to both tables in `references/azure-targets.md`.
3. Add any new action to `references/versions.md`.
4. Remove the target from the "Out of scope" list in `azure-targets.md` and from the
   "Not yet" table in the repository README.
5. **Test it against a real repository and watch the run go green before committing.**
   An untested template is worse than no template, because it looks authoritative.

### Add a language or stack

1. Add `templates/ci-<stack>.yml`.
2. Add a `detect_<stack>()` function in `scripts/detect_stack.py` and register it in the
   detector tuple inside `find_services()`.
3. Add a row to the CI template table in `references/azure-targets.md`.

### Add a readiness check

Add a row to the right section of `references/checks.md` with a new ID, a severity and a
concrete fix. If the check is mechanical, also implement it in
`scripts/validate_workflows.py` so it is enforced rather than merely suggested.

---

## Testing a change

```bash
# manifest is well-formed
claude plugin validate .

# templates still parse and remain structurally sound
python skills/deploy-check/scripts/validate_workflows.py skills/deploy-check/templates

# detector runs against a real project
python skills/deploy-check/scripts/detect_stack.py --root /path/to/some/repo
```

Validating `templates/` directly reports three expected artifacts, because a raw template
contains every auth branch simultaneously: `no-leftover-tokens`, `id-token-unused` and
`publish-profile-az-cli`. Test group 5 asserts that set exactly.

If a template starts failing anything else — `permissions-scope`, `oidc-id-token`,
`action-pinned`, `deploy-trigger-scope`, `auth-target-compatible` — that is a genuine
regression, and every generated workflow would inherit it.

---

## Design rules that must not be relaxed

These exist because breaking them produces output that is confidently wrong, which is more
dangerous than no output:

- Never invent an Azure resource name, subscription ID, tenant ID or credential.
- Never write a secret value into a generated file, and never echo one found in a repo —
  report file and line only.
- Never overwrite an existing workflow in place; write `.generated.yml` and diff.
- Never claim a deployment will succeed. Azure state is always `Unknown`.
- Never run a deployment command.
- Every finding is labelled `Verified`, `Assumed` or `Unknown`.
