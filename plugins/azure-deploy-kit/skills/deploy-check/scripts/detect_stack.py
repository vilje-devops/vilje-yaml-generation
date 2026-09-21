#!/usr/bin/env python3
"""Deterministic repository facts for the azure-deploy-kit deploy-check skill.

Emits JSON describing what an application repository *is*, so the model does judgement
on facts instead of re-deriving them differently on every run.

Standard library only. No third-party imports, so it runs anywhere Python 3.8+ exists.

SAFETY: this script never emits the *value* of anything that looks like a credential.
Suspected secrets are reported as file, line number and rule name only.

Usage:
    python detect_stack.py --root . --json
    python detect_stack.py --print-fields    # what to collect by hand if Python is absent
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".env.d",
    "dist", "build", ".next", ".nuxt", "out", "target", "bin", "obj",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "coverage", ".tox",
    "vendor", ".gradle", ".idea", ".vs", ".terraform", "site-packages",
}
SOURCE_EXT = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py", ".cs", ".go",
    ".java", ".rb", ".php", ".env.example", ".yml", ".yaml", ".json", ".toml",
}
MAX_FILE_BYTES = 512_000
MAX_SCAN_FILES = 4000


# --------------------------------------------------------------------------- utils

def walk(root):
    """Yield file paths, skipping vendor and build directories."""
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude ".git" exactly - a startswith(".git") test would also drop ".github".
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            count += 1
            if count > MAX_SCAN_FILES:
                return
            yield os.path.join(dirpath, fn)


def read(path, limit=MAX_FILE_BYTES):
    try:
        if os.path.getsize(path) > limit:
            return ""
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def load_json(path):
    try:
        return json.loads(read(path) or "{}")
    except (ValueError, TypeError):
        return {}


def rel(root, path):
    try:
        return os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


def run_git(root, *args):
    try:
        out = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


# --------------------------------------------------------------------------- git

def detect_git(root):
    info = {"is_repo": False, "default_branch": None, "current_branch": None,
            "owner": None, "repo": None, "remote": None}
    if run_git(root, "rev-parse", "--is-inside-work-tree") != "true":
        return info
    info["is_repo"] = True
    info["current_branch"] = run_git(root, "branch", "--show-current")

    head = run_git(root, "symbolic-ref", "refs/remotes/origin/HEAD")
    if head:
        info["default_branch"] = head.rsplit("/", 1)[-1]
    else:
        # No origin/HEAD (common on a fresh clone). Fall back to the local branch.
        info["default_branch"] = info["current_branch"]

    remote = run_git(root, "remote", "get-url", "origin")
    if remote:
        info["remote"] = remote
        m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", remote)
        if m:
            info["owner"], info["repo"] = m.group(1), m.group(2)
    return info


# --------------------------------------------------------------------- node/python

NODE_FRAMEWORKS = [
    ("next", "Next.js"), ("nuxt", "Nuxt"), ("@remix-run/react", "Remix"),
    ("@angular/core", "Angular"), ("@nestjs/core", "NestJS"), ("svelte", "Svelte"),
    ("astro", "Astro"), ("vite", "Vite"), ("react", "React"), ("vue", "Vue"),
    ("express", "Express"), ("fastify", "Fastify"), ("koa", "Koa"),
    ("@azure/functions", "Azure Functions (Node)"),
]
PY_FRAMEWORKS = [
    ("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask"),
    ("litestar", "Litestar"), ("starlette", "Starlette"), ("aiohttp", "aiohttp"),
    ("azure-functions", "Azure Functions (Python)"),
]
STATIC_OUTPUT = {
    "Next.js": ".next", "Nuxt": ".output/public", "Angular": "dist",
    "Vite": "dist", "React": "build", "Vue": "dist", "Svelte": "build",
    "Astro": "dist", "Remix": "build",
}


def detect_node(root, d):
    pkg_path = os.path.join(d, "package.json")
    pkg = load_json(pkg_path)
    if not pkg:
        return None

    scripts = pkg.get("scripts") or {}
    deps = {}
    deps.update(pkg.get("dependencies") or {})
    deps.update(pkg.get("devDependencies") or {})

    frameworks = [label for key, label in NODE_FRAMEWORKS if key in deps]

    lockfiles = [
        ("pnpm-lock.yaml", "pnpm", "pnpm install --frozen-lockfile"),
        ("yarn.lock", "yarn", "yarn install --frozen-lockfile"),
        ("package-lock.json", "npm", "npm ci"),
        ("bun.lockb", "bun", "bun install --frozen-lockfile"),
    ]
    pm, lockfile, install = "npm", None, "npm install"
    for name, mgr, cmd in lockfiles:
        if os.path.exists(os.path.join(d, name)):
            pm, lockfile, install = mgr, name, cmd
            break

    version, source = None, None
    nvmrc = os.path.join(d, ".nvmrc")
    if os.path.exists(nvmrc):
        version, source = (read(nvmrc).strip().lstrip("v") or None), ".nvmrc"
    elif (pkg.get("engines") or {}).get("node"):
        version, source = pkg["engines"]["node"], "package.json engines.node"

    primary = frameworks[0] if frameworks else None
    return {
        "language": "JavaScript/TypeScript",
        "frameworks": frameworks,
        "package_manager": pm,
        "lockfile": lockfile,
        "runtime_version": {"value": version, "source": source},
        "install_command": install,
        "build_command": f"{pm} run build" if "build" in scripts else None,
        "test_command": f"{pm} test" if "test" in scripts else None,
        "lint_command": f"{pm} run lint" if "lint" in scripts else None,
        "start_command": f"{pm} start" if "start" in scripts else None,
        "build_output": STATIC_OUTPUT.get(primary),
        "scripts": sorted(scripts.keys()),
        "manifest": rel(root, pkg_path),
        "typescript": "typescript" in deps,
    }


def detect_python(root, d):
    files = {f: os.path.join(d, f) for f in (
        "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
        "poetry.lock", "uv.lock", ".python-version",
    ) if os.path.exists(os.path.join(d, f))}
    if not files:
        return None

    blob = " ".join(read(p).lower() for f, p in files.items() if f.endswith((".txt", ".toml", ".py")))
    frameworks = [label for key, label in PY_FRAMEWORKS if key in blob]

    if "uv.lock" in files:
        pm, lockfile, install = "uv", "uv.lock", "uv sync --frozen"
    elif "poetry.lock" in files:
        pm, lockfile, install = "poetry", "poetry.lock", "poetry install --no-interaction"
    elif "requirements.txt" in files:
        pm, lockfile, install = "pip", "requirements.txt", "pip install -r requirements.txt"
    else:
        pm, lockfile, install = "pip", None, "pip install ."

    version, source = None, None
    if ".python-version" in files:
        version, source = read(files[".python-version"]).strip() or None, ".python-version"
    elif "pyproject.toml" in files:
        m = re.search(r'requires-python\s*=\s*["\']([^"\']+)', read(files["pyproject.toml"]))
        if m:
            version, source = m.group(1), "pyproject.toml requires-python"

    has_tests = os.path.isdir(os.path.join(d, "tests")) or "pytest" in blob
    return {
        "language": "Python",
        "frameworks": frameworks,
        "package_manager": pm,
        "lockfile": lockfile,
        "runtime_version": {"value": version, "source": source},
        "install_command": install,
        "build_command": None,
        "test_command": "pytest" if has_tests else None,
        "lint_command": "ruff check ." if "ruff" in blob else None,
        "start_command": None,
        "build_output": None,
        "manifest": rel(root, next(iter(files.values()))),
    }


def detect_dotnet(root, d):
    projects = [f for f in os.listdir(d) if f.endswith((".csproj", ".fsproj"))] \
        if os.path.isdir(d) else []
    if not projects:
        return None
    proj_path = os.path.join(d, projects[0])
    content = read(proj_path)
    m = re.search(r"<TargetFramework>net([\d.]+)</TargetFramework>", content)
    version = f"{m.group(1)}.x" if m else None
    return {
        "language": "C#/.NET",
        "frameworks": ["ASP.NET Core"] if "Microsoft.NET.Sdk.Web" in content else [],
        "package_manager": "nuget",
        "lockfile": "packages.lock.json" if os.path.exists(
            os.path.join(d, "packages.lock.json")) else None,
        "runtime_version": {"value": version, "source": "TargetFramework"},
        "install_command": f'dotnet restore "{rel(root, proj_path)}"',
        "build_command": f'dotnet build "{rel(root, proj_path)}" -c Release',
        "test_command": None,
        "lint_command": None,
        "start_command": None,
        "build_output": "publish",
        "manifest": rel(root, proj_path),
        "project_path": rel(root, proj_path),
    }


# ------------------------------------------------------------------- code scanning

PORT_PATTERNS = [
    re.compile(r"\.listen\s*\(\s*(?:process\.env\.(\w+)\s*(?:\|\||\?\?)\s*)?(\d{2,5})"),
    re.compile(r"uvicorn\.run\([^)]*port\s*=\s*(?:int\()?[^,)]*?(\d{2,5})"),
    re.compile(r"--port[= ](\d{2,5})"),
    re.compile(r"EXPOSE\s+(\d{2,5})"),
    re.compile(r"app\.run\([^)]*port\s*=\s*(\d{2,5})"),
]
ENV_PATTERNS = [
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]{2,})"),
    re.compile(r"process\.env\[['\"]([A-Z][A-Z0-9_]{2,})['\"]\]"),
    re.compile(r"os\.environ(?:\.get)?[\[(]\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"Environment\.GetEnvironmentVariable\(\s*\"([A-Z][A-Z0-9_]{2,})\""),
    re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]{2,})"),
]

# Value is NEVER captured or emitted - only the rule name and location.
SECRET_RULES = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("db_connection_string_with_password",
     re.compile(r"(?i)(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|amqp)://[^:\s'\"]+:[^@\s'\"]{4,}@")),
    ("sql_connection_string",
     re.compile(r"(?i)(?:Server|Data Source)\s*=[^;'\"]+;[^'\"]*(?:Password|Pwd)\s*=\s*[^;'\"\s]{4,}")),
    ("azure_storage_key",
     re.compile(r"(?i)AccountKey\s*=\s*[A-Za-z0-9+/]{40,}={0,2}")),
    ("assigned_credential_literal",
     re.compile(r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?token|"
                r"auth[_-]?token|client[_-]?secret)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[abpsr]-[A-Za-z0-9-]{10,}\b")),
]
# Lines matching these are placeholders, not real secrets.
PLACEHOLDER = re.compile(
    r"(?i)(your[_-]?|example|placeholder|changeme|change[_-]me|xxxx|<[^>]+>|\.\.\.|"
    r"dummy|sample|fake|todo|\$\{|\{\{|process\.env|os\.environ|getenv|secrets\.)"
)
SECRET_SAFE_FILES = re.compile(
    r"(?i)(\.env\.example|\.env\.sample|\.env\.template|readme|\.md$|test|spec|"
    r"fixture|mock|__tests__|\.lock$|package-lock\.json)"
)


def scan_sources(root):
    ports, env_vars, secrets, dockerfiles = set(), {}, [], []
    compose, iac, workflows = [], [], []

    for path in walk(root):
        r = rel(root, path)
        base = os.path.basename(path).lower()

        if base.startswith("dockerfile"):
            dockerfiles.append(r)
        if base in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
            compose.append(r)
        if base.endswith((".bicep", ".tf")) or base == "azuredeploy.json":
            iac.append(r)
        if "/.github/workflows/" in "/" + r and base.endswith((".yml", ".yaml")):
            workflows.append(r)

        ext = os.path.splitext(path)[1]
        scannable = ext in SOURCE_EXT or base.startswith("dockerfile") or base == "procfile"
        if not scannable:
            continue

        content = read(path)
        if not content:
            continue

        for pat in PORT_PATTERNS:
            for m in pat.finditer(content):
                val = m.group(m.lastindex or 1)
                if val and val.isdigit() and 80 <= int(val) <= 65535:
                    ports.add(int(val))

        for pat in ENV_PATTERNS:
            for m in pat.finditer(content):
                env_vars.setdefault(m.group(1), set()).add(r)

        if SECRET_SAFE_FILES.search(r):
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            if len(line) > 1000 or PLACEHOLDER.search(line):
                continue
            for rule, pat in SECRET_RULES:
                if pat.search(line):
                    # Location and rule only. The matched text is deliberately discarded.
                    secrets.append({"file": r, "line": lineno, "rule": rule})
                    break

    return {
        "ports": sorted(ports),
        "env_vars": {k: sorted(v)[:3] for k, v in sorted(env_vars.items())},
        "suspected_hardcoded_secrets": secrets[:50],
        "dockerfiles": sorted(dockerfiles),
        "compose_files": sorted(compose),
        "iac_files": sorted(iac),
        "existing_workflows": sorted(workflows),
    }


# ------------------------------------------------------------------------- services

def find_services(root):
    """A directory holding a manifest is a candidate deployable service."""
    markers = ("package.json", "requirements.txt", "pyproject.toml", "setup.py", "Pipfile")
    dirs = set()
    for path in walk(root):
        base = os.path.basename(path)
        if base in markers or base.endswith((".csproj", ".fsproj")):
            dirs.add(os.path.dirname(path))

    services = []
    for d in sorted(dirs):
        for detector in (detect_node, detect_python, detect_dotnet):
            info = detector(root, d)
            if info:
                info["path"] = rel(root, d)
                info["has_dockerfile"] = any(
                    os.path.exists(os.path.join(d, n))
                    for n in ("Dockerfile", "dockerfile", "Dockerfile.prod")
                )
                services.append(info)
                break
    return services


def health_hint(root):
    for path in walk(root):
        if os.path.splitext(path)[1] not in {".js", ".ts", ".py", ".cs", ".jsx", ".tsx"}:
            continue
        m = re.search(r"['\"](/(?:api/)?health(?:z|check)?)['\"]", read(path))
        if m:
            return m.group(1)
    return None


FIELDS = """Collect these by hand if Python is unavailable:

git.default_branch, git.owner, git.repo
services[].path, .language, .frameworks, .package_manager, .lockfile
services[].runtime_version{value,source}, .install_command, .build_command,
            .test_command, .lint_command, .start_command, .build_output, .has_dockerfile
ports (from listen(/EXPOSE/--port)
env_vars (names only, from process.env.X / os.environ / GetEnvironmentVariable)
dockerfiles, compose_files, iac_files, existing_workflows
suspected_hardcoded_secrets (file + line + rule ONLY - never the value)
health_endpoint
"""


def main():
    ap = argparse.ArgumentParser(description="Detect deployment-relevant repository facts.")
    ap.add_argument("--root", default=".", help="repository root (default: .)")
    ap.add_argument("--json", action="store_true", help="emit JSON (default)")
    ap.add_argument("--print-fields", action="store_true",
                    help="list the fields to collect manually, then exit")
    args = ap.parse_args()

    if args.print_fields:
        print(FIELDS)
        return 0

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(json.dumps({"error": f"not a directory: {root}"}))
        return 2

    scan = scan_sources(root)
    services = find_services(root)

    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": root.replace("\\", "/"),
        "git": detect_git(root),
        "services": services,
        "service_count": len(services),
        "is_monorepo": len(services) > 1,
        "health_endpoint": health_hint(root),
        **scan,
        "notes": [],
    }

    if not services:
        result["notes"].append(
            "No recognised manifest found. Inspect the repository manually before generating.")
    if result["is_monorepo"]:
        result["notes"].append(
            f"{len(services)} services detected - resolve the monorepo question before generating.")
    if scan["suspected_hardcoded_secrets"]:
        result["notes"].append(
            "Possible hardcoded secrets found. Report file and line ONLY - never the value. "
            "These are regex matches and include false positives; confirm before reporting.")
    if not scan["existing_workflows"]:
        result["notes"].append("No existing GitHub Actions workflows.")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
