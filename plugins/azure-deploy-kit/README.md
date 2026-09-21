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

Templates are expected to fail `no-leftover-tokens` and nothing else. If a template starts
failing `permissions-scope`, `oidc-id-token`, `action-pinned` or `deploy-trigger-scope`,
that is a genuine regression — every generated workflow would inherit it.

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
