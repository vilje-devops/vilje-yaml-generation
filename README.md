# Vilje DevOps — Claude Code plugin marketplace

Internal Claude Code plugins for Vilje Tech. Currently one plugin:

| Plugin | Command | Purpose |
|---|---|---|
| **azure-deploy-kit** | `/deploy-check` | Analyze a repo for Azure deployment readiness and generate application-specific GitHub Actions CI/CD YAML |

---

## Install

Run these once per developer, from anywhere:

```bash
claude plugin marketplace add https://github.com/vilje-devops/vilje-yaml-generation
claude plugin install azure-deploy-kit@vilje-devops
```

Then open any application repository and run:

```
/deploy-check
```

> The marketplace name `vilje-devops` is defined in `.claude-plugin/marketplace.json`;
> it is what developers type after `@` when installing.

### Update

```bash
claude plugin update azure-deploy-kit
```

Because the marketplace points at a Git repository, every developer gets the new version
on their next update. Bump `version` in `plugins/azure-deploy-kit/.claude-plugin/plugin.json`
when you ship a change.

### Verify the install

```bash
claude plugin list
```

---

## Usage

```
/deploy-check                      # auto: analyze, then offer to generate
/deploy-check analyze              # read-only readiness report, writes nothing
/deploy-check generate             # ask questions, then write the workflow files
/deploy-check validate             # check existing workflows in .github/workflows/
/deploy-check generate --target container-apps
/deploy-check validate --run-build # also run the project's real build and tests
```

### What it produces

- `.github/workflows/ci.yml` and `.github/workflows/deploy.yml`, filled from tested
  templates and matched to the application it actually found
- `DEPLOYMENT.md` — a plain-language guide answering five questions: what was created,
  how the deployment works, what you must configure, how to run it, and how to tell whether
  it worked. Includes a pre-deployment checklist and troubleshooting for *your* app.
  Written to be readable by developers, team leads and non-technical readers alike
- `.deploy-check.yml` — your confirmed answers, so re-runs do not re-interrogate you
  (contains choices and names only, never secrets)

### What it deliberately does **not** do

**It never deploys.** No `az` deploy commands, no `gh workflow run`, no `git push`. It
writes files; a developer reviews them, creates the Azure resources and secrets, and
pushes.

It also never invents an Azure resource name, subscription ID or credential — anything it
cannot determine becomes a visible `{{TOKEN}}` with a `# TODO(you):` comment and a line in
the report.

### Supported targets

| Supported today | Not yet |
|---|---|
| Azure App Service (code) | Azure Functions |
| Azure App Service (container) | AKS |
| Azure Container Apps | Virtual Machines |
| Azure Static Web Apps | Bicep / Terraform provisioning |

Stacks: Node/TypeScript, Python, .NET. Anything else is analyzed, and the generated
workflow is marked `Assumed` in the report.

### Supported authentication methods

| Method | App Service | Container Apps | Static Web Apps |
|---|---|---|---|
| OIDC federated credentials *(default)* | yes | yes | n/a |
| Service principal secret | yes | yes | n/a |
| **Publish profile** | **yes** | no | no |

Static Web Apps uses its own deployment token rather than any of the three.

Publish profile is an App Service feature: Container Apps and Static Web Apps have no
publish profile, so that combination is rejected rather than generated (check `AZ-07`).

**Existing conventions are preserved.** If a repo already has workflows, the detector
reads how they authenticate and keeps that method by default - including the existing
secret names. Changing method is something the skill asks about, never does silently.

---

## Honest limits

The skill has no access to Azure or to your GitHub repository settings. It therefore
**cannot** verify that your resources exist, that your identity has the right role, that
your secrets are set, or that the deployment will succeed. Everything in that category is
reported as `Unknown`, and every report repeats it. A green validation means the YAML is
well-formed — nothing more.

---

## Repository layout

```
.claude-plugin/marketplace.json          marketplace metadata (this repo)
plugins/azure-deploy-kit/
  .claude-plugin/plugin.json             plugin manifest
  skills/deploy-check/
    SKILL.md                             the /deploy-check command: 6 phases, hard rules
    references/
      checks.md                          the readiness rubric (IDs, severity, fix)
      questions.md                       what to ask, and what never to ask
      azure-targets.md                   target selection and template mapping
      versions.md                        pinned action versions - single source of truth
      auth.md                            OIDC, service principal, publish profile
      report-format.md                   DEPLOYMENT.md structure
    templates/                           tested workflow YAML with {{TOKEN}} placeholders
    examples/
      DEPLOYMENT.example.md              a complete worked report
    scripts/
      detect_stack.py                    deterministic repo facts -> JSON
      validate_workflows.py              YAML, structure and security checks
      validate_report.py                 DEPLOYMENT.md structure and safety checks
  tests/
    run_tests.py                         test suite - all three auth methods
    fixtures/                            8 workflow fixtures, valid and invalid
```

## Contributing

See [plugins/azure-deploy-kit/README.md](plugins/azure-deploy-kit/README.md) for how to
add an Azure target or a stack, and for the quarterly action-version refresh.

Before committing a change:

```bash
claude plugin validate ./plugins/azure-deploy-kit
python plugins/azure-deploy-kit/tests/run_tests.py
python plugins/azure-deploy-kit/skills/deploy-check/scripts/validate_workflows.py \
       plugins/azure-deploy-kit/skills/deploy-check/templates
```

A raw template holds all three auth branches at once, so validating the `templates/`
directory legitimately reports three artifact failures: `no-leftover-tokens`,
`id-token-unused` and `publish-profile-az-cli`. Those combinations only coexist *before*
pruning. `run_tests.py` group 5 pins this — any **other** failure is a real defect that
every generated workflow would inherit.
