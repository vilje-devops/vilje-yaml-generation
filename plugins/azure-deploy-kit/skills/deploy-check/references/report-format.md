# Report format

Two outputs: a short chat summary, and `DEPLOYMENT.md` written to the repo root.

`DEPLOYMENT.md` is built from `templates/DEPLOYMENT.template.md` — fill it in, do not
author it freehand. Same rule as the workflow templates, for the same reason: a report
written from memory comes out different every run.

After writing it, validate it:

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/deploy-check/scripts/validate_report.py" DEPLOYMENT.md
```

## Who reads this

Three audiences, one document:

- **The developer** who will push the code and debug the first failure.
- **The team lead** who wants to know what changed and what it costs to adopt.
- **Someone non-technical** who needs to understand what happens and what is still needed.

Write so the third person can follow it. That means: no unexplained jargon, short
sentences, and every instruction stating *where* to click or *what* to run. When a term is
unavoidable (OIDC, publish profile, App Service), explain it in one plain sentence the
first time it appears.

This does not mean vague. "Push to `main` and the workflow runs" is simple *and* precise.
"Deployment is triggered automatically via the configured CI/CD pipeline" is jargon that
says less.

## Evidence labels

Every factual claim carries one. This is what separates a useful report from a
confident-sounding guess.

| Label | Means | Example |
|---|---|---|
| `Verified` | You read the file or ran the command and observed the result | "Verified: `package.json` defines `build` as `vite build`." |
| `Assumed` | Inferred from convention, not observed | "Assumed: the app listens on 3000 — no explicit bind found, this is the Express default." |
| `Unknown` | Needs user input or Azure/GitHub access you do not have | "Unknown: whether `rg-prod-weu` exists. I cannot query Azure." |

Never upgrade an Assumed to a Verified because it is probably right. Anything about live
Azure or GitHub state is **always** Unknown — you have no access to either.

In the report, mark them inline as `[Verified]`, `[Assumed]`, `[Unknown]` so a reader
scanning the page can see instantly which rows are solid.

## The five questions

The report answers five questions, in this order, as its five main sections. A reader
should be able to jump to the one they need.

| # | Section heading | Answers |
|---|---|---|
| 1 | What did the skill create? | files written, what was analyzed, what problems were found |
| 2 | How does the deployment work? | the pipeline in plain steps |
| 3 | What do I need to configure? | secrets, variables, Azure resources, the checklist |
| 4 | How do I run the deployment? | the exact trigger and what to do |
| 5 | How do I know whether it succeeded? | where to look, what was validated, troubleshooting |

Before them sits a short header: status, Azure target, auth method, trigger, and a plain
statement that nothing has been deployed.

## Rules for filling it

1. **Never invent a value.** Every resource name, secret name, branch, path and command
   comes from the detector output, the user's confirmed answers, or a file you read. If
   you do not have it, write `{{NOT PROVIDED}}` and add it to the checklist in section 3.
2. **Secret names only, never values.** This includes publish profile XML, connection
   strings and `AZURE_CREDENTIALS` JSON. If you found a hardcoded secret in the repo,
   report the file and line, never the content.
3. **Never say the deployment succeeded, worked, or is live.** You did not run it. Say
   what will happen when the developer pushes.
4. **Keep the disclaimer verbatim.** The exact sentence is in the template. Do not soften
   or reword it.
5. **Delete what does not apply.** No Dockerfile means no container rows. Publish profile
   means no federated-credential section. An empty section with "N/A" is noise.
6. **Every "Failed" and "Not performed" row states a reason.** "actionlint not installed",
   "no Azure access", "`--run-build` not set".
7. **Troubleshooting entries must match this app.** Generic advice is filler. If the app
   binds a hardcoded port, the 502 row is relevant and says so; if it does not, drop it.

## Chat summary

Separate from the file. Short — the detail belongs in `DEPLOYMENT.md`.

```
Target:    Azure App Service (code) — no Dockerfile found
Auth:      publish profile — kept, your existing workflows already use it
Verdict:   Blocked — 2 blockers
Blockers:  RUN-01 hardcoded port 8000 (src/main.py:42)
           SEC-01 connection string in source (src/db.py:11)
Files:     .github/workflows/ci.yml (new), deploy.yml (new), DEPLOYMENT.md (new)
Next:      fix the 2 blockers, create 1 GitHub secret, then push to main
Full guide: DEPLOYMENT.md
```

## Tone

- Specific over hedged: "binds a hardcoded 8000 at `src/main.py:42`", not "may have port
  configuration issues".
- One sentence of why per blocker. The reader needs the reason to prioritise.
- Plain words over ceremony. "You need to create this secret" beats "the following
  prerequisite must be satisfied".
- No praise, no filler. The report is a work order.
- If you could not determine something, say so in a sentence and move on. An honest
  Unknown is worth more than a plausible guess.
