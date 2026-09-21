#!/usr/bin/env python3
"""Validate generated GitHub Actions workflows for the azure-deploy-kit skill.

Reports three lists: passed, failed, and NOT PERFORMED (with the reason). The third list
is the honest part - never drop it from the report.

This checks syntax, structure and security hygiene. It cannot tell you whether an Azure
deployment will succeed: Azure resources, role assignments, quotas and network paths are
all unverifiable from here.

PyYAML is used when importable; without it the script falls back to regex checks and says
so. Standard library otherwise.

Usage:
    python validate_workflows.py .github/workflows
    python validate_workflows.py .github/workflows/deploy.yml --repo-root .
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

try:
    import yaml  # type: ignore
    HAVE_YAML = True
except ImportError:
    yaml = None
    HAVE_YAML = False

OK, FAIL, SKIP = "pass", "fail", "skipped"

# A literal that is clearly a secret rather than a ${{ secrets.X }} reference.
INLINE_SECRET = re.compile(
    r"(?i)\b(password|client[_-]?secret|api[_-]?key|access[_-]?token|auth[_-]?token|"
    r"connection[_-]?string)\b\s*:\s*['\"]?(?!\$\{\{)[^\s'\"#]{8,}")
UNPINNED = re.compile(r"uses:\s*([\w.-]+/[\w.-]+(?:/[\w.-]+)*)@(main|master|HEAD)\b")
USES = re.compile(r"uses:\s*([\w.-]+/[\w.-]+(?:/[\w.-]+)*)@([^\s#]+)")
SECRET_REF = re.compile(r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
LEFTOVER_TOKEN = re.compile(r"\{\{[#/]?[A-Z_a-z][^}]*\}\}")


class Report:
    def __init__(self):
        self.rows = []

    def add(self, status, check, detail, where=None):
        self.rows.append({"status": status, "check": check, "detail": detail, "where": where})

    def counts(self):
        return {s: sum(1 for r in self.rows if r["status"] == s) for s in (OK, FAIL, SKIP)}


def workflow_files(target):
    if os.path.isfile(target):
        return [target]
    if os.path.isdir(target):
        return sorted(
            os.path.join(target, f) for f in os.listdir(target)
            if f.endswith((".yml", ".yaml"))
        )
    return []


def parse(path, rep):
    """Parse a workflow. YAML 1.1 turns the key `on` into boolean True - normalise it."""
    text = open(path, encoding="utf-8", errors="ignore").read()
    if not HAVE_YAML:
        rep.add(SKIP, "yaml-parse", "PyYAML not installed - structural checks are regex-based "
                                    "and weaker. Install with: pip install pyyaml", path)
        return None, text
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        rep.add(FAIL, "yaml-parse", f"YAML does not parse: {exc}", path)
        return None, text
    if not isinstance(doc, dict):
        rep.add(FAIL, "yaml-parse", "Workflow root is not a mapping.", path)
        return None, text
    if True in doc and "on" not in doc:
        doc["on"] = doc.pop(True)
    rep.add(OK, "yaml-parse", "Parses as valid YAML.", path)
    return doc, text


def check_structure(doc, path, rep):
    for key in ("on", "jobs"):
        if key in doc and doc[key]:
            rep.add(OK, f"has-{key}", f"`{key}:` present.", path)
        else:
            rep.add(FAIL, f"has-{key}", f"`{key}:` missing - the workflow will never run.", path)

    jobs = doc.get("jobs") or {}
    if not isinstance(jobs, dict):
        return
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        if job.get("runs-on") or job.get("uses"):
            rep.add(OK, "job-runs-on", f"Job `{name}` declares a runner.", path)
        else:
            rep.add(FAIL, "job-runs-on", f"Job `{name}` has no `runs-on:`.", path)
        if job.get("timeout-minutes"):
            rep.add(OK, "job-timeout", f"Job `{name}` sets `timeout-minutes`.", path)
        else:
            rep.add(SKIP, "job-timeout",
                    f"Job `{name}` has no `timeout-minutes` - a hung job burns 6h of runner "
                    f"time (CI-08, info).", path)


def check_permissions(doc, text, path, rep):
    top = doc.get("permissions")
    if top is None:
        rep.add(FAIL, "permissions-scope",
                "No workflow-level `permissions:`. The default grants broad write access to "
                "GITHUB_TOKEN (SEC-03). Add `permissions: {contents: read}`.", path)
    elif top == "write-all":
        rep.add(FAIL, "permissions-scope", "`permissions: write-all` is maximal privilege (SEC-03).", path)
    else:
        rep.add(OK, "permissions-scope", "Workflow-level `permissions:` is set.", path)

    uses_azure_login = "azure/login@" in text
    uses_creds = re.search(r"creds\s*:", text) is not None
    if uses_azure_login and not uses_creds:
        # OIDC path: the job calling azure/login needs id-token: write.
        has_id_token = False
        for job in (doc.get("jobs") or {}).values():
            if isinstance(job, dict):
                perms = job.get("permissions") or {}
                if isinstance(perms, dict) and perms.get("id-token") == "write":
                    has_id_token = True
        if isinstance(top, dict) and top.get("id-token") == "write":
            has_id_token = True
        if has_id_token:
            rep.add(OK, "oidc-id-token", "`id-token: write` present for azure/login OIDC.", path)
        else:
            rep.add(FAIL, "oidc-id-token",
                    "azure/login is used without `creds:` (OIDC), but no `id-token: write` "
                    "permission is granted. Login will fail at runtime. See auth.md.", path)


PUBLISH_PROFILE = re.compile(r"publish-profile\s*:")
AZURE_LOGIN = re.compile(r"uses\s*:\s*[Aa]zure/login@")
SP_CREDS = re.compile(r"creds\s*:")
AZ_CLI_STEP = re.compile(r"^\s*(?:-\s*)?run\s*:.*\baz\s+\w", re.M)
TARGET_ACTIONS = {
    "App Service": re.compile(r"[Aa]zure/webapps-deploy@"),
    "Container Apps": re.compile(r"[Aa]zure/container-apps-deploy-action@"),
    "Static Web Apps": re.compile(r"[Aa]zure/static-web-apps-deploy@"),
}
# Publish profiles are an App Service feature. Nothing else accepts one.
PUBLISH_PROFILE_INCOMPATIBLE = ("Container Apps", "Static Web Apps")


def check_auth_compatibility(doc, text, path, rep):
    """Reject auth/target combinations that cannot work (AZ-07)."""
    has_profile = bool(PUBLISH_PROFILE.search(text))
    has_login = bool(AZURE_LOGIN.search(text))
    has_creds = bool(SP_CREDS.search(text))
    targets = [name for name, pat in TARGET_ACTIONS.items() if pat.search(text)]

    if has_profile:
        method = "publish profile"
    elif has_login and has_creds:
        method = "service principal secret"
    elif has_login:
        method = "OIDC"
    else:
        method = None

    if method:
        rep.add(OK, "auth-method-detected",
                f"Authenticates with: {method}"
                + (f" | deploy target(s): {', '.join(targets)}" if targets else ""), path)

    # The check the user asked for: publish profile against a target that has none.
    if has_profile:
        bad = [t for t in targets if t in PUBLISH_PROFILE_INCOMPATIBLE]
        if bad:
            rep.add(FAIL, "auth-target-compatible",
                    f"Publish profile is used with {', '.join(bad)}, which has no publish "
                    f"profile - only App Service does. This workflow cannot authenticate. "
                    f"Use OIDC or a service principal secret instead (AZ-07).", path)
        else:
            rep.add(OK, "auth-target-compatible",
                    "Publish profile is used with App Service - a valid combination.", path)

        # A publish profile does not authenticate the az CLI.
        if AZ_CLI_STEP.search(text):
            rep.add(FAIL, "publish-profile-az-cli",
                    "A publish profile does not authenticate the az CLI, but this workflow "
                    "has an `az ...` run step and no azure/login. That step will fail. "
                    "Remove it, or switch to OIDC / service principal secret (AZ-07).", path)

    # Privilege that is granted but never used.
    if not (has_login and not has_creds):
        grants = [doc.get("permissions")] + [
            j.get("permissions") for j in (doc.get("jobs") or {}).values()
            if isinstance(j, dict)]
        if any(isinstance(g, dict) and g.get("id-token") == "write" for g in grants):
            rep.add(FAIL, "id-token-unused",
                    "`id-token: write` is granted but this workflow does not use OIDC. "
                    "Remove it - it is privilege with no purpose (SEC-03).", path)


def check_triggers(doc, path, rep):
    on = doc.get("on")
    if isinstance(on, dict) and "pull_request_target" in on:
        rep.add(FAIL, "pull-request-target",
                "`pull_request_target` grants repository secrets to workflows triggered by "
                "forks. If it also checks out the PR head, this is remote code execution "
                "(SEC-04).", path)
    # `on: push:` with a null value means every branch, as does a push: mapping with no
    # branches/tags filter. Both must fail (CI-02).
    if isinstance(on, dict) and "push" in on:
        push = on.get("push")
        scoped = isinstance(push, dict) and any(
            push.get(k) for k in ("branches", "branches-ignore", "tags", "tags-ignore", "paths")
        )
        if scoped:
            rep.add(OK, "deploy-trigger-scope", "Push trigger is scoped.", path)
        else:
            rep.add(FAIL, "deploy-trigger-scope",
                    "`on.push` has no branch or tag filter - this runs on every push to "
                    "every branch (CI-02).", path)
    elif isinstance(on, (str, list)) and "push" in on:
        rep.add(FAIL, "deploy-trigger-scope",
                "`on: push` in short form has no branch filter - it runs on every push "
                "to every branch (CI-02).", path)
    if isinstance(doc.get("concurrency"), (dict, str)):
        rep.add(OK, "concurrency", "`concurrency:` set - simultaneous deploys prevented.", path)
    else:
        rep.add(SKIP, "concurrency",
                "No `concurrency:` group. Two pushes can deploy at once (CI-07, warning).", path)


def check_actions(text, path, rep):
    unpinned = UNPINNED.findall(text)
    if unpinned:
        for action, ref in unpinned:
            rep.add(FAIL, "action-pinned",
                    f"`{action}@{ref}` follows a moving branch - the action's code can change "
                    f"under you (SEC-05). Pin to a major tag or a commit SHA.", path)
    else:
        found = USES.findall(text)
        if found:
            rep.add(OK, "action-pinned", f"All {len(found)} action references are pinned.", path)


def check_secrets(text, path, rep):
    hits = [(i, ln) for i, ln in enumerate(text.splitlines(), 1)
            if INLINE_SECRET.search(ln) and "${{" not in ln and not ln.strip().startswith("#")]
    if hits:
        for lineno, _ in hits:
            # Location only - the matched text is never emitted.
            rep.add(FAIL, "no-inline-secrets",
                    f"Line {lineno} looks like an inline credential literal. Use "
                    f"${{{{ secrets.NAME }}}} (SEC-02).", path)
    else:
        rep.add(OK, "no-inline-secrets", "No inline credential literals found.", path)

    names = sorted(set(SECRET_REF.findall(text)))
    if names:
        rep.add(OK, "secret-references",
                f"References {len(names)} repository secret(s): {', '.join(names)}. "
                f"Each must exist in GitHub before the first run.", path)


def check_leftover_tokens(text, path, rep):
    """A {{TOKEN}} that survived generation means a value was never filled in."""
    leftovers = sorted(set(
        m.group(0) for m in LEFTOVER_TOKEN.finditer(text)
        if not m.group(0).startswith("${{")
    ))
    if leftovers:
        rep.add(FAIL, "no-leftover-tokens",
                f"Unsubstituted template tokens remain: {', '.join(leftovers[:8])}. "
                f"Each must be replaced or documented with a # TODO(you): comment.", path)
    else:
        rep.add(OK, "no-leftover-tokens", "No unsubstituted template tokens.", path)


def check_referenced_paths(text, repo_root, path, rep):
    """Verify paths the workflow points at actually exist in the repository."""
    checked, missing = 0, []
    for key in ("cache-dependency-path", "file", "app_location", "output_location", "api_location"):
        for m in re.finditer(rf'{key}\s*:\s*["\']?([^"\'\n#]+)', text):
            val = m.group(1).strip()
            if not val or "${{" in val or "{{" in val or val in (".", "./"):
                continue
            checked += 1
            if not os.path.exists(os.path.join(repo_root, val.lstrip("./"))):
                missing.append(f"{key}: {val}")
    if missing:
        for item in missing:
            rep.add(FAIL, "referenced-paths", f"Path does not exist in the repo - {item}", path)
    elif checked:
        rep.add(OK, "referenced-paths", f"All {checked} referenced path(s) exist.", path)


def run_actionlint(target, rep):
    exe = shutil.which("actionlint")
    if not exe:
        rep.add(SKIP, "actionlint",
                "actionlint is not installed - expression and context errors were NOT checked. "
                "Install: https://github.com/rhysd/actionlint")
        return
    try:
        out = subprocess.run([exe, target], capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            rep.add(OK, "actionlint", "actionlint reported no problems.")
        else:
            for line in (out.stdout or out.stderr).strip().splitlines()[:25]:
                rep.add(FAIL, "actionlint", line.strip())
    except (OSError, subprocess.SubprocessError) as exc:
        rep.add(SKIP, "actionlint", f"actionlint could not be run: {exc}")


DEPLOY_ACTION = re.compile(
    r"[Aa]zure/(?:webapps-deploy|container-apps-deploy-action|static-web-apps-deploy)@")
PATHS_KEY = re.compile(r"(?m)^[ \t]+paths(?:-ignore)?:")


def check_cross_workflow(files, rep):
    """More than one deploying workflow in a repo needs path filters (CI-09)."""
    deploying = []
    for path in files:
        text = open(path, encoding="utf-8", errors="ignore").read()
        if DEPLOY_ACTION.search(text):
            deploying.append((path, bool(PATHS_KEY.search(text))))

    if len(deploying) < 2:
        return
    unfiltered = [os.path.basename(p) for p, has in deploying if not has]
    if unfiltered:
        rep.add(FAIL, "multi-deploy-paths-filter",
                f"{len(deploying)} workflows deploy from this repository and "
                f"{len(unfiltered)} have no `on.push.paths:` filter "
                f"({', '.join(unfiltered)}). Every push deploys every service - a change "
                f"to one app redeploys the others (CI-09).")
    else:
        rep.add(OK, "multi-deploy-paths-filter",
                f"All {len(deploying)} deploying workflows scope their triggers with "
                f"`paths:`.")


def unverifiable(rep):
    """State plainly what this tool structurally cannot check."""
    for detail in (
        "Azure resources exist with the right SKU and runtime stack - no Azure access.",
        "The deploying identity holds the required role on the resource - no Azure access.",
        "The OIDC federated credential subject matches this workflow - no Azure access.",
        "Repository secrets actually exist in GitHub - no repo settings access.",
        "The application starts and serves traffic once deployed - not executed.",
    ):
        rep.add(SKIP, "not-verifiable", detail)


def main():
    ap = argparse.ArgumentParser(description="Validate GitHub Actions workflows.")
    ap.add_argument("target", nargs="?", default=".github/workflows",
                    help="workflow file or directory (default: .github/workflows)")
    ap.add_argument("--repo-root", default=".", help="repository root for path checks")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args()

    rep = Report()
    files = workflow_files(args.target)
    if not files:
        rep.add(FAIL, "workflows-found", f"No workflow files at: {args.target}")
    else:
        for path in files:
            doc, text = parse(path, rep)
            if doc:
                check_structure(doc, path, rep)
                check_permissions(doc, text, path, rep)
                check_auth_compatibility(doc, text, path, rep)
                check_triggers(doc, path, rep)
            check_actions(text, path, rep)
            check_secrets(text, path, rep)
            check_leftover_tokens(text, path, rep)
            check_referenced_paths(text, args.repo_root, path, rep)
        check_cross_workflow(files, rep)
        run_actionlint(args.target, rep)

    unverifiable(rep)
    counts = rep.counts()

    if args.json:
        print(json.dumps({"counts": counts, "results": rep.rows}, indent=2))
        return 1 if counts[FAIL] else 0

    labels = {OK: "PASSED", FAIL: "FAILED", SKIP: "NOT PERFORMED / ADVISORY"}
    for status in (FAIL, OK, SKIP):
        rows = [r for r in rep.rows if r["status"] == status]
        if not rows:
            continue
        print(f"\n{labels[status]} ({len(rows)})")
        print("-" * 70)
        for r in rows:
            where = f"  [{os.path.basename(r['where'])}]" if r.get("where") else ""
            print(f"  {r['check']}{where}\n      {r['detail']}")

    print(f"\n{'=' * 70}")
    print(f"passed: {counts[OK]}   failed: {counts[FAIL]}   not performed: {counts[SKIP]}")
    print("YAML validation confirms syntax and structure only. It does not prove the")
    print("deployment will succeed - Azure resources, permissions, quotas and network")
    print("paths are unverified.")
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
