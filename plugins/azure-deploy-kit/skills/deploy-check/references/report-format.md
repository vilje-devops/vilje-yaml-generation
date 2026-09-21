# Report format

Two outputs: a short chat summary, and `DEPLOYMENT.md` written to the repo root.

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

## Chat summary

Short. The detail belongs in the file.

```
Target:    Azure Container Apps (recommended — Dockerfile present, scale-to-zero wanted)
Verdict:   Blocked — 2 blockers
Blockers:  RUN-01 hardcoded port 8000 (src/main.py:42)
           SEC-01 connection string in source (src/db.py:11)
Files:     .github/workflows/ci.yml (new), deploy.yml (new), DEPLOYMENT.md (new)
Next:      fix the 2 blockers, create 3 GitHub secrets, then push to main
Full report: DEPLOYMENT.md
```

## DEPLOYMENT.md structure

Use these eight sections in this order.

### 1. Summary

Verdict (Blocked / Ready with caveats / Cannot determine), the chosen target with its
one-line rationale, and counts by severity. Date and plugin version.

### 2. Detected architecture

What the app actually is. Table of: language, framework, package manager, runtime version
and where it is pinned, build command, start command, listening port, containerized
yes/no, services found. Label each row.

### 3. Readiness findings

Grouped `Blockers` / `Warnings` / `Info`. Each finding:

```
**RUN-01** · blocker · Verified
Server binds a hardcoded port 8000 (`src/main.py:42`).
App Service injects PORT; a hardcoded port returns 502.
Fix: `uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))`
```

Then a `Skipped checks` line naming the sections that did not apply and why.

### 4. Generated files

Table: path, purpose, new or modified. If anything was written as `.generated.yml`
because a file already existed, say so here and show what differs.

### 5. Validation results

Three lists, all three always present:

- **Passed** — what was checked and passed.
- **Failed** — what was checked and failed.
- **Not performed** — what was not checked, each with its reason
  ("`actionlint` not installed", "no Azure access", "`--run-build` not set").

Then verbatim, not paraphrased:

> YAML validation confirms syntax and structure only. It does not prove the deployment
> will succeed. Azure resources, permissions, quotas and network paths are unverified.

### 6. Required GitHub configuration

Every secret and variable, by name. Values never appear.

| Name | Type | Holds | Where to get it |
|---|---|---|---|
| `AZURE_CLIENT_ID` | secret | App registration client ID | Entra ID > App registrations |

Plus any GitHub Environment to create, and its required reviewers.

### 7. Required Azure configuration

Resources that must exist, each marked `Unknown - verify in the portal`. Include the
exact federated credential subject string when OIDC was chosen. Include the role
assignments and their scope.

### 8. Remaining manual steps

Numbered, in order, each one action. Ends with the developer pushing:

```
1. Fix RUN-01 and SEC-01 (see section 3).
2. Rotate the connection string exposed in src/db.py — it is in git history.
3. Create the resource group and Container App (section 7).
4. Add the federated credential with subject: repo:acme/api:ref:refs/heads/main
5. Add the 3 repository secrets (section 6).
6. Review .github/workflows/deploy.yml.
7. Push to main to trigger the first deploy.
```

Step 7 is the developer's action. **Never perform it.**

## Tone

- Specific over hedged: "binds a hardcoded 8000 at `src/main.py:42`", not "may have port
  configuration issues".
- One sentence of why per blocker. The reader needs the reason to prioritise.
- No praise, no filler. The report is a work order.
- If you could not determine something, say that in a sentence and move on. An honest
  Unknown is worth more than a plausible guess.
