---
name: deploy-check
description: >
  Analyze an application repository for Azure deployment readiness and generate
  application-specific GitHub Actions CI/CD workflow YAML. Inspects languages,
  frameworks, build/test/start commands, runtime versions, ports, environment
  variables, Dockerfiles, databases and existing workflows; reports blockers as a
  scored readiness rubric; asks only for facts the repo cannot reveal (Azure target
  service, environments, trigger branch, auth method); then fills tested templates to
  produce .github/workflows/ci.yml and deploy.yml for Azure App Service, Azure
  Container Apps or Azure Static Web Apps, and validates the result. Use when the user
  wants to deploy an app to Azure, set up or review GitHub Actions CI/CD, generate or
  fix deployment YAML, or check whether a codebase is deployment-ready. This skill
  writes and validates files only - it never executes a deployment.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Azure Deploy Kit

Generate **accurate, application-specific** GitHub Actions YAML for deploying to Azure.

You produce and validate files. **You never deploy.** A developer reviews your output,
creates the Azure resources and secrets, and pushes. Say so whenever it matters.

`${CLAUDE_PLUGIN_ROOT}` is this plugin's install directory. All reference and template
paths below are relative to `${CLAUDE_PLUGIN_ROOT}/skills/deploy-check/`.

## Hard rules

These are not preferences. Breaking one makes the output dangerous.

1. **Never invent** Azure resource names, subscription IDs, tenant IDs, client IDs,
   resource groups, registry names, or domains. Unknown becomes a `{{TOKEN}}` placeholder
   plus a line in the "You must configure" section of the report.
2. **Never write a secret value into a generated file.** Credentials appear only as
   `${{ secrets.NAME }}`. If you find a hardcoded secret in the repo, report the
   file, line and variable name only — never the value, not even partially.
3. **Never ask the user to paste a secret into chat.** Ask for names, not values.
4. **Never overwrite an existing workflow in place.** If the target file exists, write
   `<name>.generated.yml` beside it and show a diff. The user decides what to keep.
5. **Never claim a deployment will succeed.** YAML validity proves syntax, nothing more.
   You have no Azure access and cannot verify resources, permissions or quotas.
6. **Never run a deployment command.** No `az webapp deploy`, no `gh workflow run`,
   no `git push`. Generating the file is where your job ends.
7. **Label every finding** Verified / Assumed / Unknown. See `references/report-format.md`.
8. **Ask before writing files.** Present the file plan, get approval, then write.

## Modes

Read the argument the user passed. Default per the command file.

| Mode | Does | Writes files |
|---|---|---|
| `analyze` | Phases 1-2. Readiness report only. | No |
| `generate` | Phases 1-4 plus 5-6. Full path. | Yes, after approval |
| `validate` | Phase 5 on existing workflows, then report. | No |

Flags: `--target <service>` skips the hosting question. `--run-build` permits Phase 5 to
execute the project's real build and test commands (off by default — slow, and often
needs services that are not running locally).

---

## Phase 1 — Discovery

Run the deterministic detector first. It produces the facts; you do the judgement.

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/deploy-check/scripts/detect_stack.py" --root . --json
```

Try `python`, then `py`. If neither runs, gather the same fields by hand with
Glob/Grep/Read — `--print-fields` lists exactly what to collect.

The detector reports: languages, frameworks, package managers, lockfiles, build/test/start
commands, pinned runtime versions, listening ports, referenced environment variables,
Dockerfiles, compose files, IaC files, existing workflows, the services found in a
monorepo, and the locations of suspected hardcoded secrets.

Then read what the script cannot interpret: the entry point, the Dockerfile, and any
existing workflow in `.github/workflows/`. **Do not read `.env` files for their values.**
Read `.env.example` freely; from a real `.env`, take key names only.

If the detector found more than one deployable service, resolve the monorepo question
before continuing — see `references/azure-targets.md`, section Monorepos.

## Phase 2 — Readiness assessment

Apply every check in `references/checks.md`. Each has an ID, a severity and a fix.
Report them grouped by severity, each labelled Verified / Assumed / Unknown.

A `blocker` means the deployment will fail or will leak secrets — not that the code is
untidy.

Do not give a "ready to deploy" verdict while any blocker is open or while a required
fact is Unknown. Name the specific unresolved thing instead.

In `analyze` mode, stop here and offer to continue with `generate`.

## Phase 3 — Ask for missing inputs

Read `references/questions.md`. It defines the question set, the order, and — importantly
— which questions to **skip** because the detector already answered them.

Use `AskUserQuestion`, grouped, at most 4 questions per call. Ask only what the repository
genuinely cannot tell you. Asking a developer something their own `package.json` already
states destroys trust in the rest of the report.

Write the confirmed answers to `.deploy-check.yml` at the repo root so later runs do not
re-interrogate. If that file already exists, read it first and ask only about the gaps.

## Phase 4 — Generate

1. Pick templates using the decision table in `references/azure-targets.md`.
2. Read the chosen template files from `templates/`.
3. Read `references/versions.md` and pin every action to the version recorded there.
4. Substitute every `{{TOKEN}}`. Remove `{{#if ...}}` blocks that do not apply.
   Token semantics are in `templates/TEMPLATES.md`.
5. Any token you cannot fill from repo facts or user answers stays as a visible
   placeholder with a `# TODO(you):` comment directly above it.
6. Present the file plan — path, purpose, new or modified — and get approval.
7. Write the files. Respect hard rule 4 for anything that already exists.

Generate the minimum set that actually works. A repo that needs one workflow gets one
workflow. Do not emit Docker Compose, Bicep or extra environments nobody asked for.

## Phase 5 — Validate

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/deploy-check/scripts/validate_workflows.py" .github/workflows
```

It checks YAML parse, required workflow keys, action pinning, `permissions:` scope,
OIDC `id-token: write` when `azure/login` is used, secret-reference sanity, hardcoded
secret patterns, and whether referenced paths and scripts exist in the repo.

If `actionlint` is on PATH, run it too — it catches expression and context errors this
script does not. It is not installed by default; report its absence rather than silently
skipping it.

With `--run-build`, additionally run the detected build and test commands locally.

Report each validation as passed, failed, or **not performed** with the reason. The
"not performed" list is the honest part of the report — never omit it.

## Phase 6 — Final report

Write `DEPLOYMENT.md` at the repo root using the exact structure in
`references/report-format.md`. It must end with two sections the developer acts on:

- **Required GitHub configuration** — every secret and variable name, what each holds,
  and where to obtain it. Names only, never values.
- **Required Azure configuration** — the resources that must exist, and the federated
  credential subject string if OIDC was chosen. See `references/auth.md`.

Close with the remaining manual steps, in order, ending at "push to `<branch>` to trigger
the workflow" — which the developer does, not you.

## Reference files

Load these only when the phase calls for them.

| File | Read during |
|---|---|
| `references/checks.md` | Phase 2 — the readiness rubric |
| `references/questions.md` | Phase 3 — what to ask, what to skip |
| `references/azure-targets.md` | Phase 4 — target and template selection |
| `references/versions.md` | Phase 4 — pinned action versions |
| `references/auth.md` | Phase 4 and 6 — OIDC and alternatives |
| `references/report-format.md` | Phase 2 and 6 — report structure |
| `templates/TEMPLATES.md` | Phase 4 — token conventions |
