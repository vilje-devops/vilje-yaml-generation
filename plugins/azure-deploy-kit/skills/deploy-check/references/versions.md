# Pinned action versions

**Single source of truth.** Templates carry these versions; when a version changes, edit
this file and the templates together. Never let a generated workflow use a version that
is not listed here, and never use `@main` or `@master`.

Last verified against the GitHub Releases API: **2026-09-21**.

## Core

| Action | Pin | Notes |
|---|---|---|
| `actions/checkout` | `v7` | |
| `actions/setup-node` | `v7` | use `cache: npm\|pnpm\|yarn` |
| `actions/setup-python` | `v7` | use `cache: pip\|poetry` |
| `actions/setup-dotnet` | `v6` | |
| `actions/upload-artifact` | `v7` | |
| `actions/download-artifact` | `v7` | **Pin to v7 deliberately.** `v8` exists, but these two actions version independently and a matching major is the safe pairing. Do not mix v7 upload with v8 download. |

## Azure

| Action | Pin | Notes |
|---|---|---|
| `azure/login` | `v3` | Requires `permissions: id-token: write` on the job when using OIDC |
| `azure/webapps-deploy` | `v3` | App Service, code and container. **v3, not v2** - see the trap below. |
| `azure/static-web-apps-deploy` | `v1` | Only a `v1` major is published |
| `azure/container-apps-deploy-action` | `v2` | Container Apps |
| `azure/cli` | `v3` | For steps the dedicated actions do not cover |

## Container build

| Action | Pin | Notes |
|---|---|---|
| `docker/login-action` | `v4` | |
| `docker/build-push-action` | `v7` | set `platforms: linux/amd64` unless ARM is deliberately configured |
| `docker/setup-buildx-action` | `v3` | only needed for cache or multi-platform builds |

## Runners

| Label | Use |
|---|---|
| `ubuntu-latest` | Default for everything |
| `windows-latest` | Only for a genuine Windows-only build (full .NET Framework, Windows-specific native deps) |

## A trap in the refresh command

`azure/webapps-deploy` publishes `v3` tags, but the GitHub *releases* API still reports
`v2.2.19` as "latest". Reading only `releases/latest` pins the wrong major and silently
downgrades a repo that already runs v3.

For any Azure action, check the **tags**, not just the latest release:

```bash
curl -s "https://api.github.com/repos/Azure/webapps-deploy/tags?per_page=100" \
  | grep '"name"' | head -5
```

## Policy

- **Pin to the major only** (`@v7`), not `@v7.0.1`. Majors get security patches; exact
  patch pins go stale silently.
- **For a high-security repo**, pin third-party actions to a full commit SHA with the
  version in a trailing comment. `actions/*` and `azure/*` are first-party and a major
  tag is acceptable.
- **Re-verify quarterly.** Refresh with:

  ```bash
  for r in actions/checkout actions/setup-node actions/setup-python actions/setup-dotnet \
           actions/upload-artifact actions/download-artifact Azure/login Azure/webapps-deploy \
           Azure/static-web-apps-deploy Azure/container-apps-deploy-action \
           docker/build-push-action docker/login-action; do
    printf "%-40s " "$r"
    curl -s "https://api.github.com/repos/$r/releases/latest" | grep '"tag_name"' | cut -d'"' -f4
  done
  ```

- If a repo already uses a **newer** major than listed here, do not downgrade it. Keep
  the repo's version, and note in the report that this file is behind.
- Equally, do not *upgrade* a working repo's actions as a side effect of generating a new
  workflow. Changing `actions/checkout@v4` to `@v7` in a pipeline that already works is a
  change the team did not ask for. Mention it as an optional improvement instead.
