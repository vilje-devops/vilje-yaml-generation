# Vilje DevOps — Claude Code plugin marketplace

Internal Claude Code plugins for Vilje Tech. Currently one plugin:

| Plugin | Command | Purpose |
|---|---|---|
| **azure-deploy-kit** | `/deploy-check` | Analyze a repo for Azure deployment readiness and generate application-specific GitHub Actions CI/CD YAML |

---

## Install

Run these once per laptop, from any folder — they change your global Claude config, so the
directory does not matter:

```bash
claude plugin marketplace add https://github.com/vilje-devops/vilje-yaml-generation
claude plugin install azure-deploy-kit@vilje-devops
```

Restart Claude Code, then open **an application repository** and run:

```
/deploy-check
```

`/deploy-check` reads whatever repo it is sitting in, so run it in the app you want
workflows for — not in this one.

> The marketplace name `vilje-devops` comes from `.claude-plugin/marketplace.json`. It is
> what you type after `@` when installing.

### Check which version you have

```bash
claude plugin list
```

```
❯ azure-deploy-kit@vilje-devops
  Version: 0.1.2
  Scope: user
  Status: ✔ enabled
```

For more detail — including whether the skill loaded correctly — use:

```bash
claude plugin details azure-deploy-kit
```

A healthy install reports exactly one skill:

```
Component inventory
  Skills (1)  deploy-check
```

If it says `Skills (2)  deploy-check, deploy-check`, your install is stale. Follow
**Update** below.

### Update to a new release

Two commands. Refresh the catalogue, then install:

```bash
claude plugin marketplace update vilje-devops
claude plugin install azure-deploy-kit@vilje-devops
```

Restart Claude Code, then confirm with `claude plugin list`.

**Use `install`, not `claude plugin update`.** Refreshing the marketplace removes the entry
for whatever version you had, because that version is no longer in the catalogue. Running
`claude plugin update` at that point fails with:

```
✘ Failed to update plugin "azure-deploy-kit": Plugin "azure-deploy-kit" is not installed
```

`install` handles both a first install and an upgrade, so it is the one command to
remember. If it ever refuses, uninstall first:

```bash
claude plugin uninstall azure-deploy-kit
claude plugin install azure-deploy-kit@vilje-devops
```

<details>
<summary>Why a reinstall is sometimes needed</summary>

Claude Code caches each plugin in a folder named after its **version string**:

```
~/.claude/plugins/cache/vilje-devops/azure-deploy-kit/0.1.1/
```

If a version number is ever reused for different code, the cached folder is served instead
of the new code — and `claude plugin update` reports success while nothing actually
changes. That happened once during this plugin's development: an update printed
`updated from 0.1.1 to 0.1.0` while still serving the older templates.

`0.1.2` onwards has a clean cache, so `claude plugin update` works normally. Reinstalling
is only needed when coming from `0.1.0` or `0.1.1`.

**Maintainers: never reuse a version number.** Always increment `version` in
`plugins/azure-deploy-kit/.claude-plugin/plugin.json` when shipping a change, even a tiny
one. That is what makes "which version am I running?" answerable.

</details>

### Uninstall

```bash
claude plugin uninstall azure-deploy-kit
claude plugin marketplace remove vilje-devops
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

**House default.** For a repo with no existing workflows, the skill recommends
**publish profile for App Service** (what our other App Service repos use) and **OIDC for
Container Apps**. All three are always offered. OIDC is the more secure choice - nothing
stored in GitHub, nothing to rotate - and a team that can create Entra app registrations
should consider standardising on it. To change the recommendation for everyone, edit the
*House auth default* table in
`plugins/azure-deploy-kit/skills/deploy-check/references/questions.md`.

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
