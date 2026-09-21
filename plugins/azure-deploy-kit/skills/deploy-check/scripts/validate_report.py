#!/usr/bin/env python3
"""Validate a generated DEPLOYMENT.md for the azure-deploy-kit skill.

Checks that the report actually answers the five questions, carries the disclaimer
verbatim, labels its facts, leaks no secret values, and never claims a deployment
succeeded. Structure and safety only - it cannot judge whether the content is true.

Standard library only.

Usage:
    python validate_report.py DEPLOYMENT.md
    python validate_report.py DEPLOYMENT.md --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

OK, FAIL, WARN = "pass", "fail", "warn"

# The five questions, in order. Matched loosely on the distinctive words so a reworded
# heading still passes, but a missing section does not.
REQUIRED_SECTIONS = [
    ("what did the skill create", r"^#{1,3}\s*1\.\s*what did the skill create"),
    ("how does the deployment work", r"^#{1,3}\s*2\.\s*how does the deployment work"),
    ("what do i need to configure", r"^#{1,3}\s*3\.\s*what do i need to configure"),
    ("how do i run the deployment", r"^#{1,3}\s*4\.\s*how do i run the deployment"),
    ("how do i know whether it succeeded", r"^#{1,3}\s*5\.\s*how do i know whether it succeeded"),
]

DISCLAIMER = (
    "YAML validation confirms syntax and structure only. It does not prove the deployment "
    "will succeed. Azure resources, permissions, quotas and network paths are unverified."
)

# Claims the skill is never allowed to make - it does not deploy.
FALSE_SUCCESS = re.compile(
    r"(?i)\b(deployment (was |has been )?(successful|succeeded|completed)"
    r"|successfully deployed"
    r"|(the )?(app|application|site) is (now )?live"
    r"|deployed successfully"
    r"|is now (running|deployed) (in|on) azure)\b")

# A secret value that escaped into the document. Names are fine; values are not.
SECRET_VALUE = [
    ("publish profile XML", re.compile(r"<publishData|<publishProfile")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("service principal JSON with a secret", re.compile(r'"clientSecret"\s*:\s*"[^"]+"')),
    ("connection string with a password",
     re.compile(r"(?i)(?:Password|Pwd)\s*=\s*[^;\s\"'<{]{4,}")),
    ("database URL with credentials",
     re.compile(r"(?i)(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql)://[^:\s]+:[^@\s]{4,}@")),
    ("assigned credential literal",
     re.compile(r"(?i)\b(?:password|client[_-]?secret|api[_-]?key|access[_-]?token)\b"
                r"\s*[:=]\s*[\"'][^\"'\n]{8,}[\"']")),
]
# Lines that are obviously instructional rather than a leaked value.
PLACEHOLDER_LINE = re.compile(
    r"(?i)(\{\{|\$\{\{|<your|your-|example|placeholder|never|paste|do not|"
    r"secret name|names only|<name>|xxx)")

LEFTOVER_TOKEN = re.compile(r"\{\{(?!NOT PROVIDED)[A-Za-z_#/][^}]*\}\}")
EVIDENCE_LABEL = re.compile(r"\[(Verified|Assumed|Unknown)\]")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


class Report:
    def __init__(self):
        self.rows = []

    def add(self, status, check, detail=""):
        self.rows.append({"status": status, "check": check, "detail": detail})

    def counts(self):
        return {s: sum(1 for r in self.rows if r["status"] == s) for s in (OK, FAIL, WARN)}


def strip_comments(text):
    return HTML_COMMENT.sub("", text)


def check_sections(body, rep):
    lines = body.splitlines()
    for label, pattern in REQUIRED_SECTIONS:
        rx = re.compile(pattern, re.I)
        if any(rx.match(ln.strip()) for ln in lines):
            rep.add(OK, f"section: {label}", "present")
        else:
            rep.add(FAIL, f"section: {label}",
                    "missing - the report must answer all five questions as numbered "
                    "sections (see references/report-format.md)")


def check_disclaimer(body, rep):
    # The disclaimer is rendered as a blockquote, so strip the leading "> " markers and
    # any emphasis before comparing - otherwise they split the sentence mid-match.
    plain = re.sub(r"(?m)^\s*>\s?", "", body).replace("*", "").replace("`", "")
    normalised = " ".join(plain.split())
    if " ".join(DISCLAIMER.split()) in normalised:
        rep.add(OK, "disclaimer", "present and unmodified")
    else:
        rep.add(FAIL, "disclaimer",
                "the validation disclaimer is missing or reworded. It must appear verbatim "
                "in section 5.")


def check_no_false_success(body, rep):
    hits = [(i, ln.strip()) for i, ln in enumerate(body.splitlines(), 1)
            if FALSE_SUCCESS.search(ln)]
    if hits:
        for lineno, ln in hits:
            rep.add(FAIL, "no-success-claim",
                    f"line {lineno} claims a deployment happened: {ln[:90]!r}. "
                    f"The skill does not deploy.")
    else:
        rep.add(OK, "no-success-claim", "no claim that a deployment has run")


def check_no_secret_values(body, rep):
    found = []
    for lineno, line in enumerate(body.splitlines(), 1):
        if PLACEHOLDER_LINE.search(line):
            continue
        for label, pattern in SECRET_VALUE:
            if pattern.search(line):
                # Report the location and the rule - never the matched text.
                found.append((lineno, label))
                break
    if found:
        for lineno, label in found:
            rep.add(FAIL, "no-secret-values",
                    f"line {lineno} looks like it contains a {label}. The report carries "
                    f"secret NAMES only.")
    else:
        rep.add(OK, "no-secret-values", "no secret values detected")


def check_placeholders(body, rep):
    leftovers = sorted({m.group(0) for m in LEFTOVER_TOKEN.finditer(body)})
    if leftovers:
        rep.add(FAIL, "no-unfilled-tokens",
                f"unfilled template tokens remain: {', '.join(leftovers[:8])}"
                + (" ..." if len(leftovers) > 8 else "")
                + ". Fill each from real analysis, or use {{NOT PROVIDED}} and add a "
                  "checklist item.")
    else:
        rep.add(OK, "no-unfilled-tokens", "every token was filled")

    if "{{NOT PROVIDED}}" in body:
        n = body.count("{{NOT PROVIDED}}")
        rep.add(WARN, "not-provided-markers",
                f"{n} value(s) marked NOT PROVIDED - each needs a matching item in the "
                f"section 3 checklist")


def check_evidence_labels(body, rep):
    labels = EVIDENCE_LABEL.findall(body)
    if not labels:
        rep.add(FAIL, "evidence-labels",
                "no [Verified] / [Assumed] / [Unknown] labels found. Every factual claim "
                "about the app or about Azure must carry one.")
        return
    rep.add(OK, "evidence-labels", f"{len(labels)} label(s) used: "
            + ", ".join(f"{l}={labels.count(l)}" for l in sorted(set(labels))))
    if "Unknown" not in labels:
        rep.add(WARN, "unknown-label-expected",
                "no [Unknown] label anywhere. Azure-side state is always Unknown - the "
                "skill cannot verify resources, roles or secrets.")


def check_actionable_content(body, rep):
    checklist = len(re.findall(r"^\s*-\s*\[[ xX]\]", body, re.M))
    if checklist:
        rep.add(OK, "pre-deployment-checklist", f"{checklist} checklist item(s)")
    else:
        rep.add(FAIL, "pre-deployment-checklist",
                "section 3 must end with a tickable pre-deployment checklist")

    if re.search(r"(?i)^#{2,4}.*(if it fails|troubleshoot|common cause)", body, re.M):
        rep.add(OK, "troubleshooting", "troubleshooting guidance present")
    else:
        rep.add(FAIL, "troubleshooting",
                "section 5 must include troubleshooting guidance for this app")

    if re.search(r"(?i)\bactions tab\b", body):
        rep.add(OK, "where-to-look", "tells the reader where to check the run")
    else:
        rep.add(WARN, "where-to-look",
                "section 5 should name the GitHub Actions tab explicitly")

    if re.search(r"(?i)nothing has been deployed|no deployment has been run", body):
        rep.add(OK, "not-deployed-notice", "states up front that nothing was deployed")
    else:
        rep.add(FAIL, "not-deployed-notice",
                "the header must state plainly that nothing has been deployed")


def main():
    ap = argparse.ArgumentParser(description="Validate a generated DEPLOYMENT.md.")
    ap.add_argument("path", nargs="?", default="DEPLOYMENT.md")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rep = Report()
    if not os.path.isfile(args.path):
        rep.add(FAIL, "file-exists", f"not found: {args.path}")
    else:
        raw = open(args.path, encoding="utf-8", errors="ignore").read()
        body = strip_comments(raw)
        if HTML_COMMENT.search(raw):
            rep.add(WARN, "template-comments-removed",
                    "HTML comments from the template are still present - delete them from "
                    "the generated file")
        check_sections(body, rep)
        check_disclaimer(body, rep)
        check_no_false_success(body, rep)
        check_no_secret_values(body, rep)
        check_placeholders(body, rep)
        check_evidence_labels(body, rep)
        check_actionable_content(body, rep)

    counts = rep.counts()
    if args.json:
        print(json.dumps({"counts": counts, "results": rep.rows}, indent=2))
        return 1 if counts[FAIL] else 0

    labels = {OK: "PASSED", FAIL: "FAILED", WARN: "WARNING"}
    for status in (FAIL, WARN, OK):
        rows = [r for r in rep.rows if r["status"] == status]
        if not rows:
            continue
        print(f"\n{labels[status]} ({len(rows)})")
        print("-" * 70)
        for r in rows:
            print(f"  {r['check']}" + (f"\n      {r['detail']}" if r["detail"] else ""))

    print(f"\n{'=' * 70}")
    print(f"passed: {counts[OK]}   failed: {counts[FAIL]}   warnings: {counts[WARN]}")
    print("Structure and safety only - this cannot verify that the content is accurate.")
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
