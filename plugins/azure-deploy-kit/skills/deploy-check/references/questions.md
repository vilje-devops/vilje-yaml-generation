# What to ask, and what never to ask

The measure of a good run: the developer answers 3-5 questions, none of which they feel
the tool should have worked out for itself.

## Never ask these — the repository answers them

Detect, then state what you found and let the user correct it.

| Do not ask | Detect from |
|---|---|
| What language/framework is this? | manifest files, imports, `detect_stack.py` |
| What is the build/test/start command? | `package.json` scripts, `pyproject.toml`, `Makefile`, `Dockerfile` CMD |
| Is it containerized? | presence of a `Dockerfile` |
| What Node/Python version? | `.nvmrc`, `engines`, `global.json`, `.python-version`, Dockerfile base tag |
| What port does it listen on? | source scan for `listen(`, `PORT`, `EXPOSE`, `uvicorn --port` |
| Which environment variables does it need? | source scan for `process.env.X`, `os.environ[...]`, `Configuration["X"]` |
| Do you have existing workflows? | `.github/workflows/` |
| What is the default branch? | `git symbolic-ref refs/remotes/origin/HEAD` or `git branch --show-current` |
| What is the repo name / owner? | `git remote get-url origin` |

## Never ask these — they are secrets

Ask for the **name** of a secret, never its value.

- Passwords, connection strings, API keys, tokens, certificates, publish profile XML.
- "Paste your AZURE_CREDENTIALS JSON so I can check it."

If the user volunteers a secret in chat, do not write it anywhere, tell them plainly that
it should be treated as exposed and rotated, and continue using the secret's name only.

## Ask these — the repo cannot know them

Group into `AskUserQuestion` calls of at most 4. Skip any already answered by the
detector, by a `--target` flag, or by an unambiguous detection.

### Group 1 — target and environments (always ask)

1. **Azure hosting service.** Offer your recommendation first, labelled as recommended,
   with the one-line reason. Options from `azure-targets.md`.
2. **Environments.** Production only / staging + production / dev + staging + production.
   Drives how many workflow files and which GitHub Environments.
3. **Trigger.** Push to the default branch / push to a named branch / tag push /
   manual `workflow_dispatch` only / PR checks then deploy on merge.
4. **Approval gate on production.** Yes (GitHub Environment with required reviewers) / no.

### Group 2 — auth and resources (ask when generating)

5. **Authentication method.** Ask only when the detector found no existing method.
   - `existing_auth_method` set -> **do not ask.** State what you detected and keep it.
     Only ask if the user wants to change it, or if it is incompatible with the chosen
     target (publish profile + Container Apps / Static Web Apps must change, AZ-07).
   - `existing_auth_mixed` true -> ask which to standardise on.
   - Nothing detected -> ask, and put the **house default for that target** first. See
     the table below. Always offer the alternatives; never remove a choice.
6. **Are the Azure resources already provisioned?** Yes — then ask for the resource
   **names** so the workflow is concrete. No — then leave `{{TOKEN}}` placeholders and
   list creation as a manual prerequisite.
7. **Container registry**, if a container target: Azure Container Registry / GitHub
   Container Registry (ghcr.io).
8. **Database migrations**, if migrations were detected: run in the workflow before
   deploy / run as a separate manual step / none needed.

#### House auth default

Order the options with this one first, marked `(Recommended)`. This is a team decision,
not a security ranking — change the table and the whole team changes together.

| Target | Recommend first | Also offer |
|---|---|---|
| **App Service** (code or container) | **Publish profile** | OIDC, service principal secret |
| Container Apps | OIDC | service principal secret |
| Static Web Apps | n/a — uses its own deployment token | — |

Why publish profile is first for App Service: it is what Vilje's existing App Service
repos already use, so a new repo matches the ones beside it, and it needs no Entra app
registration — which not every developer can create.

Say this in one line when you recommend it, so the choice is visible rather than silent:

> Recommending **publish profile** — it is what your other App Service repos use. OIDC is
> more secure (nothing stored in GitHub, nothing to rotate) if you can create an Entra app
> registration; say so and I will use that instead.

**Do not** make publish profile the default for Container Apps or Static Web Apps. It
cannot work there at all (AZ-07).

**To change the house default**, edit the table above. It is the single place that decides
the recommendation, so the whole team moves at once.

### Group 2b — unknown or unconfirmed stack

Ask these **only** when `has_unconfirmed_stack` is true, or a service has
`confirmed: false`. Ask for the fields listed in its `needs_user_confirmation`, and skip
any the repository already proves.

Show what you found first, so the user is correcting rather than starting blank:

> I found `pom.xml`, so this looks like Java with Maven, and `<java.version>21</java.version>`
> suggests Java 21. I have not run anything, so I need you to confirm the commands.

Then ask, in one grouped call:

- **Install command** — e.g. `mvn -B dependency:go-offline`, `go mod download`,
  `bundle install`. Offer the convention as the first option, clearly labelled as a guess.
- **Build command** — or "no build step" if the runtime needs none (PHP, Ruby).
- **Test command** — or "no tests yet". Never invent one.
- **Start command** — how Azure should run it. For App Service this usually goes in the
  portal's Startup Command, not the workflow.
- **Build output folder** — what gets deployed: `target/`, `build/libs/`, `.`, …
- **Runtime version** — only if the manifest did not state it.
- **Setup action and its version input** — `actions/setup-java@v4` with `java-version`,
  `actions/setup-go@v5` with `go-version`, and so on. `templates/ci-generic.yml` lists the
  common ones. Ask if the stack is not there.

Rules for this group:

- **Never say "your stack is not supported".** It is supported the moment the user
  confirms the commands. Say what you found, say what you need, and build it.
- **If the user does not know a command, leave that step out** rather than inventing one.
  A missing step is debuggable; a wrong one looks correct and fails in CI.
- Record every answer in the report as `[Verified]` — the user told you — and note that
  the commands came from them, not from the repository.

### Group 3 — only when the repo is ambiguous

9. **Which services to deploy**, if a monorepo was detected.
10. **Which directory is the deployable app**, if the root is not obvious.
11. **Build-time vs runtime variables**, if frontend env vars were found (they are baked
    into the bundle and become public — confirm none is a secret).

## Asking well

- Put your recommendation first and mark it `(Recommended)`, with the reason.
- Make every option a real choice; do not offer a straw man.
- If the user says "you decide", pick the recommended option and **say which you picked
  and why** — in chat and in the report.
- Prefer one round of grouped questions over three rounds of one.

## Do not write a config file

Earlier versions wrote `.deploy-check.yml` to remember the answers. That is gone.

`detect_stack.py` recovers the target, auth method, secret names, trigger branch, Azure app
name, GitHub variables and runtime pin **from the generated workflow itself**. A separate
config file adds a second source of truth that goes stale the moment someone edits the
workflow without updating it — and a stale file would be trusted over the real one.

On a re-run, read the workflow. Ask only for the one or two things it genuinely cannot
show: whether production requires reviewers, and how migrations are handled.
