#!/usr/bin/env python3
"""Test suite for azure-deploy-kit.

Covers the three Azure authentication methods and the generated report:

  1. detect_stack.py identifies the auth method used by an existing workflow
  2. validate_workflows.py passes valid combinations and FAILS impossible ones
  3. every template parses as YAML and carries the auth blocks it should
  4. no credential values appear in any template or fixture
  5. raw templates fail only the known pre-pruning artifacts
  6. the DEPLOYMENT.md template covers all five reader questions
  7. validate_report.py passes the worked example and rejects a bad report

Run from anywhere:
    python plugins/azure-deploy-kit/tests/run_tests.py
    python plugins/azure-deploy-kit/tests/run_tests.py -v     # show every assertion
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
SKILL = os.path.join(PLUGIN, "skills", "deploy-check")
DETECT = os.path.join(SKILL, "scripts", "detect_stack.py")
VALIDATE = os.path.join(SKILL, "scripts", "validate_workflows.py")
TEMPLATES = os.path.join(SKILL, "templates")
FIXTURES = os.path.join(HERE, "fixtures")

# name -> (auth method the detector must report, checks that must FAIL, checks that must PASS)
CASES = {
    # ---- valid combinations -------------------------------------------------
    "publish-profile-app-service": (
        "publish_profile", set(),
        {"auth-target-compatible", "auth-method-detected", "permissions-scope"}),
    "oidc-app-service": (
        "oidc", set(), {"oidc-id-token", "auth-method-detected"}),
    "sp-secret-app-service": (
        "service_principal_secret", set(), {"auth-method-detected", "permissions-scope"}),

    # ---- combinations that cannot work --------------------------------------
    "bad-publish-profile-container-apps": (
        "publish_profile", {"auth-target-compatible"}, set()),
    "bad-publish-profile-static-web-apps": (
        "publish_profile", {"auth-target-compatible"}, set()),
    "bad-publish-profile-az-cli": (
        "publish_profile", {"publish-profile-az-cli"}, {"auth-target-compatible"}),
    "bad-oidc-missing-id-token": (
        "oidc", {"oidc-id-token"}, {"auth-method-detected"}),
    "bad-id-token-unused": (
        "publish_profile", {"id-token-unused"}, {"auth-target-compatible"}),
}

# template -> auth blocks it must contain (publish profile is App Service only)
TEMPLATE_AUTH = {
    "deploy-app-service-code.yml": {"AUTH_OIDC", "AUTH_SP_SECRET", "AUTH_PUBLISH_PROFILE"},
    "deploy-app-service-container.yml": {"AUTH_OIDC", "AUTH_SP_SECRET", "AUTH_PUBLISH_PROFILE"},
    "deploy-container-apps.yml": {"AUTH_OIDC", "AUTH_SP_SECRET"},
}

results = []


def check(name, ok, detail=""):
    results.append((ok, name, detail))
    if VERBOSE or not ok:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"\n        {detail}" if detail and not ok else ""))


def run(args):
    out = subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=120)
    return out.returncode, out.stdout, out.stderr


# --------------------------------------------------------------- detector tests

def test_detector():
    print("\n[1] detect_stack.py - auth method detection")
    for fixture, (want_auth, _, _) in CASES.items():
        root = os.path.join(FIXTURES, fixture)
        code, stdout, stderr = run([DETECT, "--root", root])
        if code != 0:
            check(f"detector runs on {fixture}", False, stderr.strip()[:200])
            continue
        try:
            data = json.loads(stdout)
        except ValueError as exc:
            check(f"detector emits JSON for {fixture}", False, str(exc))
            continue

        got = data.get("existing_auth_method")
        check(f"{fixture}: existing_auth_method == {want_auth}",
              got == want_auth, f"got {got!r}")

        wf = data.get("workflow_auth") or []
        check(f"{fixture}: workflow_auth populated", len(wf) == 1, f"got {len(wf)} entries")

        # The detector must never emit a credential value - only names.
        if want_auth == "publish_profile" and wf:
            secret = wf[0].get("publish_profile_secret")
            check(f"{fixture}: publish profile secret NAME captured",
                  secret == "AZURE_WEBAPP_PUBLISH_PROFILE", f"got {secret!r}")


# -------------------------------------------------------------- validator tests

def test_validator():
    print("\n[2] validate_workflows.py - auth/target compatibility")
    for fixture, (_, must_fail, must_pass) in CASES.items():
        root = os.path.join(FIXTURES, fixture)
        wf_dir = os.path.join(root, ".github", "workflows")
        code, stdout, stderr = run([VALIDATE, wf_dir, "--repo-root", root, "--json"])
        try:
            data = json.loads(stdout)
        except ValueError as exc:
            check(f"validator emits JSON for {fixture}", False, f"{exc} | {stderr[:200]}")
            continue

        failed = {r["check"] for r in data["results"] if r["status"] == "fail"}
        passed = {r["check"] for r in data["results"] if r["status"] == "pass"}

        for name in must_fail:
            check(f"{fixture}: {name} FAILS as expected",
                  name in failed, f"failures were {sorted(failed)}")
        for name in must_pass:
            check(f"{fixture}: {name} passes",
                  name in passed, f"passes were {sorted(passed)}")

        # A valid fixture must have no auth-related failures at all.
        if not must_fail:
            auth_fails = {f for f in failed if "auth" in f or "id-token" in f}
            check(f"{fixture}: no auth failures", not auth_fails, f"got {sorted(auth_fails)}")


# --------------------------------------------------------------- template tests

def test_templates():
    print("\n[3] templates - parse and auth block coverage")
    try:
        import yaml
    except ImportError:
        check("PyYAML available for template parsing", False, "pip install pyyaml")
        return

    for fname in sorted(os.listdir(TEMPLATES)):
        if not fname.endswith(".yml"):
            continue
        path = os.path.join(TEMPLATES, fname)
        text = open(path, encoding="utf-8").read()
        try:
            yaml.safe_load(text)
            check(f"{fname}: parses as YAML", True)
        except yaml.YAMLError as exc:
            check(f"{fname}: parses as YAML", False, str(exc)[:200])
            continue

        want = TEMPLATE_AUTH.get(fname)
        if want is None:
            continue
        got = {a for a in ("AUTH_OIDC", "AUTH_SP_SECRET", "AUTH_PUBLISH_PROFILE")
               if "{{#if " + a + "}}" in text}
        check(f"{fname}: auth blocks == {sorted(want)}", got == want, f"got {sorted(got)}")

        # Every opened conditional must be closed.
        check(f"{fname}: conditional markers balanced",
              text.count("{{#if ") == text.count("{{/if}}"),
              f"{text.count('{{#if ')} open vs {text.count('{{/if}}')} close")

    # Container Apps must never offer a publish-profile block.
    ca = open(os.path.join(TEMPLATES, "deploy-container-apps.yml"), encoding="utf-8").read()
    check("deploy-container-apps.yml: no publish-profile input",
          "publish-profile:" not in ca)
    check("deploy-container-apps.yml: states publish profile is invalid",
          "AUTH_PUBLISH_PROFILE IS NOT VALID HERE" in ca)


# ------------------------------------------------------------------ safety test

def test_no_credential_values():
    """No fixture or template may contain anything resembling a real credential."""
    print("\n[4] safety - secrets are references, never values")
    roots = [TEMPLATES, FIXTURES]
    offenders = []
    for base in roots:
        for dirpath, _, filenames in os.walk(base):
            for fn in filenames:
                if not fn.endswith((".yml", ".yaml")):
                    continue
                p = os.path.join(dirpath, fn)
                for i, line in enumerate(open(p, encoding="utf-8").read().splitlines(), 1):
                    if line.lstrip().startswith("#"):
                        continue  # prose in a comment, not a YAML value
                    low = line.lower()
                    if ("publish-profile:" in low or "creds:" in low or
                            "client-id:" in low or "password:" in low):
                        # The value must be a ${{ secrets.X }} reference or a {{TOKEN}}.
                        if "${{" not in line and "{{" not in line:
                            offenders.append(f"{os.path.relpath(p, PLUGIN)}:{i}")
    check("no inline credential values in templates or fixtures",
          not offenders, f"found at {offenders}")


# A raw template holds ALL auth branches at once, so the validator legitimately flags
# combinations that only coexist before pruning. These are the ONLY failures allowed on an
# unfilled template - anything else would be inherited by every generated workflow.
TEMPLATE_ARTIFACT_FAILURES = {
    "no-leftover-tokens",         # {{TOKEN}} placeholders are the point of a template
    "id-token-unused",            # OIDC block sits beside the publish-profile block
    "publish-profile-az-cli",     # publish-profile block sits beside the slot-swap step
    "multi-deploy-paths-filter",  # templates/ holds 4 unrelated targets, not one repo's
                                  # workflows - CI-09 only means something per repository
}


def test_template_validation_surface():
    """Templates must fail only the known pre-pruning artifacts."""
    print("\n[5] templates - validator surface (pre-pruning artifacts only)")
    code, stdout, stderr = run([VALIDATE, TEMPLATES, "--repo-root", SKILL, "--json"])
    try:
        data = json.loads(stdout)
    except ValueError as exc:
        check("validator emits JSON for templates", False, f"{exc} | {stderr[:200]}")
        return
    failed = {r["check"] for r in data["results"] if r["status"] == "fail"}
    unexpected = failed - TEMPLATE_ARTIFACT_FAILURES
    check("templates fail only known pre-pruning artifacts",
          not unexpected,
          f"unexpected failures: {sorted(unexpected)}")
    check("templates still carry placeholders",
          "no-leftover-tokens" in failed,
          "a template with no tokens left is not a template")


REPORT_VALIDATE = os.path.join(SKILL, "scripts", "validate_report.py")
REPORT_TEMPLATE = os.path.join(SKILL, "templates", "DEPLOYMENT.template.md")
REPORT_EXAMPLE = os.path.join(SKILL, "examples", "DEPLOYMENT.example.md")

# A deliberately broken report. Every one of these defects must be caught.
BAD_REPORT = """# Deployment guide

Deployment was successful and the app is now live.

## 1. What did the skill create?

A workflow. Password = hunter2supersecret

Leftover {{AZURE_APP_NAME}} token.
"""
BAD_REPORT_MUST_FAIL = {
    "section: how does the deployment work",
    "section: what do i need to configure",
    "section: how do i run the deployment",
    "section: how do i know whether it succeeded",
    "disclaimer",
    "no-success-claim",
    "no-secret-values",
    "no-unfilled-tokens",
    "evidence-labels",
    "pre-deployment-checklist",
    "troubleshooting",
    "not-deployed-notice",
}


def test_report_template():
    """The report template must exist and cover the five questions."""
    print("\n[6] DEPLOYMENT.md template")
    for path, label in ((REPORT_TEMPLATE, "template"), (REPORT_EXAMPLE, "example")):
        check(f"{label} exists", os.path.isfile(path), path)
    if not os.path.isfile(REPORT_TEMPLATE):
        return

    text = open(REPORT_TEMPLATE, encoding="utf-8").read()
    for n, phrase in enumerate([
            "What did the skill create",
            "How does the deployment work",
            "What do I need to configure",
            "How do I run the deployment",
            "How do I know whether it succeeded"], 1):
        check(f"template has section {n}: {phrase}", phrase in text)

    check("template carries the disclaimer verbatim",
          "It does not prove the deployment" in text and
          "quotas and network paths are unverified" in text)
    check("template states nothing was deployed",
          "Nothing has been deployed" in text)
    check("template warns against secret values",
          "never shown in this document" in text)
    check("template has a pre-deployment checklist",
          "- [ ]" in text)


def test_report_validator():
    """The report linter must pass the worked example and catch a bad report."""
    print("\n[7] validate_report.py")

    code, stdout, stderr = run([REPORT_VALIDATE, REPORT_EXAMPLE, "--json"])
    try:
        data = json.loads(stdout)
    except ValueError as exc:
        check("linter emits JSON for the example", False, f"{exc} | {stderr[:200]}")
        return
    failed = {r["check"] for r in data["results"] if r["status"] == "fail"}
    check("worked example passes the linter", not failed, f"failures: {sorted(failed)}")
    check("worked example uses evidence labels",
          any(r["check"] == "evidence-labels" and r["status"] == "pass"
              for r in data["results"]))

    # Negative case: a report with every defect must be rejected.
    bad = os.path.join(HERE, "_bad_report.tmp.md")
    try:
        with open(bad, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(BAD_REPORT)
        code, stdout, stderr = run([REPORT_VALIDATE, bad, "--json"])
        data = json.loads(stdout)
        failed = {r["check"] for r in data["results"] if r["status"] == "fail"}
        missed = BAD_REPORT_MUST_FAIL - failed
        check("bad report: every planted defect is caught",
              not missed, f"missed: {sorted(missed)}")
        check("bad report: non-zero exit", code != 0, f"exit {code}")
    finally:
        if os.path.exists(bad):
            os.remove(bad)


TEAM_FIXTURE = os.path.join(FIXTURES, "team-publish-profile-monorepo")


def test_real_world_regressions():
    """The seven bugs found by the Vilje team's real workflows. None may come back."""
    print("\n[8] real-world regressions (team monorepo fixture)")
    code, stdout, stderr = run([DETECT, "--root", TEAM_FIXTURE])
    if code != 0:
        check("detector runs on the team fixture", False, stderr[:200])
        return
    d = json.loads(stdout)

    # Bug 4: runtime pinned in a workflow env: block still counts as pinned.
    pins = {s["path"]: s["runtime_version"] for s in d["services"]}
    check("bug4: backend runtime read from workflow env",
          pins.get("backend", {}).get("value") == "3.12",
          f"got {pins.get('backend')}")
    check("bug4: frontend runtime read from workflow env",
          pins.get("frontend", {}).get("value") == "22.x",
          f"got {pins.get('frontend')}")
    for path, rv in pins.items():
        check(f"bug4: {path} pin cites the workflow as its source",
              "workflows/" in (rv.get("source") or ""), f"got {rv.get('source')}")

    # Bug 3: GitHub variables are not secrets, but must still be reported.
    check("bug3: ${{ vars.X }} detected",
          "NEXT_PUBLIC_API_URL" in d["github_variables"],
          f"got {list(d['github_variables'])}")

    # Bug 5: the Azure app name lives in the workflow env block.
    names = {os.path.basename(w["file"]): w["azure_app_name"] for w in d["workflow_config"]}
    check("bug5: backend app name resolved",
          names.get("deploy-backend.yml") == "ACCENT-P-D-BACKEND", f"got {names}")
    check("bug5: frontend app name resolved",
          names.get("deploy-frontend.yml") == "ACCENT-P-D-FRONTEND", f"got {names}")

    # Bug 2: a documented install command must be flagged as deliberate.
    installs = {os.path.basename(w["file"]): w["install_commands"]
                for w in d["workflow_config"]}
    fe = installs.get("deploy-frontend.yml") or []
    check("bug2: frontend npm install detected",
          any("npm install" in i["command"] for i in fe), f"got {fe}")
    check("bug2: its explanatory comment marks it deliberate",
          any(i["has_rationale"] for i in fe if "npm install" in i["command"]),
          f"got {fe}")
    be = installs.get("deploy-backend.yml") or []
    check("bug2: pip install found inside a run: | block",
          any("pip install -r" in i["command"] for i in be), f"got {be}")
    check("bug2: BUILD-08 note raised",
          any("BUILD-08" in n for n in d["notes"]))

    # Bug 7: two deploying workflows, neither scoped by paths.
    check("bug7: both deploying workflows counted",
          d["deploy_workflow_count"] == 2, f"got {d['deploy_workflow_count']}")
    check("bug7: missing paths filters listed",
          len(d["deploy_workflows_without_paths"]) == 2,
          f"got {d['deploy_workflows_without_paths']}")

    # Auth conventions still preserved, with the team's custom secret names.
    check("team secret names preserved",
          {w.get("publish_profile_secret") for w in d["workflow_auth"]} ==
          {"AZURE_WEBAPP_PUBLISH_PROFILE_BE", "AZURE_WEBAPP_PUBLISH_PROFILE_FE"},
          f"got {[w.get('publish_profile_secret') for w in d['workflow_auth']]}")

    # Validator side: CI-09 must fire.
    wf_dir = os.path.join(TEAM_FIXTURE, ".github", "workflows")
    code, stdout, _ = run([VALIDATE, wf_dir, "--repo-root", TEAM_FIXTURE, "--json"])
    v = json.loads(stdout)
    failed = {r["check"] for r in v["results"] if r["status"] == "fail"}
    check("bug7: validator raises multi-deploy-paths-filter",
          "multi-deploy-paths-filter" in failed, f"failures: {sorted(failed)}")
    check("team fixture: auth-target-compatible passes",
          "auth-target-compatible" in {r["check"] for r in v["results"]
                                       if r["status"] == "pass"})


def test_house_auth_default():
    """The recommended auth method is a team decision held in exactly one place."""
    print("\n[10] house auth default")
    q = open(os.path.join(SKILL, "references", "questions.md"), encoding="utf-8").read()
    check("house default table exists", "#### House auth default" in q)
    check("App Service recommends publish profile first",
          "| **App Service** (code or container) | **Publish profile** |" in q)
    check("Container Apps still recommends OIDC",
          "| Container Apps | OIDC |" in q)
    check("publish profile explicitly barred as a default for Container Apps",
          "Do not** make publish profile the default for Container Apps" in q)
    check("alternatives are still offered",
          "Always offer the alternatives; never remove a choice." in q)
    check("one documented place to change it",
          "To change the house default" in q)

    a = open(os.path.join(SKILL, "references", "auth.md"), encoding="utf-8").read()
    check("auth.md defers to the house default", "House auth default" in a)
    check("auth.md keeps the security trade-off visible",
          "OIDC is the strongest" in a)

    s = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
    check("SKILL.md Phase 3 points at the house default", "House auth default" in s)


def test_pinned_versions():
    """Bugs 1 and 6: version pins and the startup-command limitation."""
    print("\n[9] versions and auth documentation")
    versions = open(os.path.join(SKILL, "references", "versions.md"), encoding="utf-8").read()
    check("bug1: webapps-deploy pinned to v3", "`azure/webapps-deploy` | `v3`" in versions)
    check("bug1: the releases-API trap is documented",
          "releases" in versions and "downgrade" in versions)
    check("bug1: no silent upgrade of a working repo", "do not *upgrade*" in versions)

    for fname in ("deploy-app-service-code.yml", "deploy-app-service-container.yml"):
        text = open(os.path.join(TEMPLATES, fname), encoding="utf-8").read()
        check(f"bug1: {fname} uses webapps-deploy@v3",
              "azure/webapps-deploy@v3" in text and "webapps-deploy@v2" not in text)

    auth = open(os.path.join(SKILL, "references", "auth.md"), encoding="utf-8").read()
    check("bug6: startup-command limitation documented",
          "startup-command` is not supported" in auth or
          "`startup-command` is not supported with publish-profile auth" in auth)
    check("bug6: portal path given", "General settings" in auth)

    checks_md = open(os.path.join(SKILL, "references", "checks.md"), encoding="utf-8").read()
    check("BUILD-08 in the rubric", "BUILD-08" in checks_md)
    check("CI-09 in the rubric", "CI-09" in checks_md)
    check("BUILD-03 accepts a workflow pin", "runtime_pins_in_workflow" in checks_md)


VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv

if __name__ == "__main__":
    print("azure-deploy-kit test suite")
    print("=" * 62)
    test_detector()
    test_validator()
    test_templates()
    test_no_credential_values()
    test_template_validation_surface()
    test_report_template()
    test_report_validator()
    test_real_world_regressions()
    test_pinned_versions()
    test_house_auth_default()

    failed = [r for r in results if not r[0]]
    print("\n" + "=" * 62)
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed, {len(results)} total")
    if failed:
        print("\nFailures:")
        for _, name, detail in failed:
            print(f"  - {name}" + (f"  ({detail})" if detail else ""))
    sys.exit(1 if failed else 0)
