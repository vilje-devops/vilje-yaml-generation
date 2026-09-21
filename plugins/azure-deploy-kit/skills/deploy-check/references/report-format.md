# Report format

Two outputs: a short chat summary, and `DEPLOYMENT.md` at the repo root.

**`DEPLOYMENT.md` is filled from `templates/DEPLOYMENT.template.md`**, which carries its own
filling rules in a header comment. Read that file in Phase 6 — you do not need this one as
well. This file covers the evidence labels (also used in Phase 2) and the chat summary.

## Evidence labels

Every factual claim carries one. This is what separates a useful report from a
confident-sounding guess.

| Label | Means |
|---|---|
| `[Verified]` | You read the file or ran the command and observed the result |
| `[Assumed]` | Inferred from convention, not observed — state the inference |
| `[Unknown]` | Needs user input, or Azure/GitHub access you do not have |

Never upgrade an Assumed to a Verified because it is probably right. Anything about live
Azure or GitHub state is **always** Unknown.

## Chat summary

Short — the detail is in the file. Do not restate the report in chat.

```
Target:    Azure App Service (code) — no Dockerfile found
Auth:      publish profile — kept, your existing workflows use it
Verdict:   Blocked — 2 blockers
Blockers:  RUN-01 hardcoded port 8000 (src/main.py:42)
           SEC-01 connection string in source (src/db.py:11)
Files:     .github/workflows/deploy.yml (new), DEPLOYMENT.md (new)
Next:      fix the 2 blockers, create 1 GitHub secret, then push to main
Full guide: DEPLOYMENT.md
```

## Tone

- Specific over hedged: "binds a hardcoded 8000 at `src/main.py:42`", not "may have port
  configuration issues".
- Plain words. "You need to create this secret", not "the following prerequisite must be
  satisfied". A non-technical reader should be able to follow it.
- One sentence of why per blocker — the reader needs it to prioritise.
- No praise, no filler. The report is a work order.
- An honest Unknown beats a plausible guess.
