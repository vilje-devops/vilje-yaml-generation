---
description: Analyze this repository for Azure deployment readiness and generate application-specific GitHub Actions CI/CD YAML
argument-hint: "[analyze|generate|validate] [--target app-service|container-apps|static-web-apps] [--run-build]"
---

Run the Azure Deploy Kit on the current repository.

Invoke the `azure-deploy-kit:deploy-check` skill using the Skill tool and follow its
instructions exactly. Pass the user's arguments through unchanged:

    $ARGUMENTS

Mode selection, if the user gave no mode argument:

- No `.github/workflows/` directory exists yet  → default to `analyze`, then offer `generate`.
- Workflows already exist                        → default to `validate`, then offer `generate`.

Never skip the analyze phase before generating files, and never write a file into
`.github/workflows/` without showing the user the plan first.
