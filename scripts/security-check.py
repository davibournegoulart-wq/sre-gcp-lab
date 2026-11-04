#!/usr/bin/env python3
"""
Security & Credential Linter for SRE GCP Lab.
Scans the working tree AND git history for leaked credentials, then checks
the stack configuration for the insecure defaults found in the 2026-11-04 audit.
"""

import os
import re
import subprocess
import sys

SECRET_PATTERNS = [
    (r"AIza[0-9A-Za-z_-]{35}", "Google API Key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private Key"),
    (r"gh[pousr]_[0-9A-Za-z]{36,}", "GitHub Token"),
    (r"xox[baprs]-[0-9A-Za-z-]{10,48}", "Slack Token"),
    (r"https://hooks\.slack\.com/services/[A-Za-z0-9/]+", "Slack Webhook URL"),
    (r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+", "Discord Webhook URL"),
    (r"sk-ant-[A-Za-z0-9_-]{20,}", "Anthropic API Key"),
    (r"sk-[A-Za-z0-9]{32,}", "OpenAI-style API Key"),
    (r"ey[A-Za-z0-9_-]{10,}\.ey[A-Za-z0-9_-]{10,}\.", "Raw JWT Token"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
]

# (file, regex, description): configuration that must never come back.
CONFIG_RULES = [
    ("docker-compose.yml", r'-\s*"\d+:\d+"', "Port published on all interfaces (use 127.0.0.1:host:container)"),
    ("docker-compose.yml", r"GF_SECURITY_ADMIN_PASSWORD=admin\b", "Grafana default admin password"),
    ("docker-compose.yml", r"--web\.enable-lifecycle", "Prometheus lifecycle API (unauthenticated /-/quit)"),
    ("app/templates/suite.html", r"<script(?![^>]*\bsrc=\"/static/)", "Inline or third-party <script> (CSP is script-src 'self')"),
    ("app/static/js/suite.js", r"\.innerHTML\s*=|insertAdjacentHTML", "innerHTML sink (stored-XSS risk, use textContent/DOM nodes)"),
    ("k8s/deployment.yaml", r":latest\b", "Mutable :latest image tag"),
    ("k8s/deployment.yaml", r"readOnlyRootFilesystem:\s*false", "Writable root filesystem"),
    ("infra/terraform/main.tf", r"ipv4_enabled\s*=\s*true", "Cloud SQL public IPv4"),
]

IGNORE_DIRS = {".git", ".terraform", "node_modules", "__pycache__", ".venv", "secrets"}
IGNORE_FILES = {"security-check.py", ".env"}


def scan_text(content, where, findings):
    for pattern, desc in SECRET_PATTERNS:
        if re.search(pattern, content):
            findings.append(f"Detected {desc} in {where}")


def scan_working_tree(findings):
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            if f in IGNORE_FILES:
                continue
            path = os.path.join(root, f)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    scan_text(fh.read(), path, findings)
            except OSError as e:
                print(f"[WARN] Could not inspect {path}: {e}")


def scan_git_history(findings):
    """A secret deleted in a later commit is still public in the history."""
    try:
        log = subprocess.run(
            ["git", "log", "--all", "-p", "--no-color", "--", ".", ":(exclude)scripts/security-check.py"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"[WARN] Could not read git history: {e}")
        return
    added = "\n".join(line[1:] for line in log.splitlines() if line.startswith("+") and not line.startswith("+++"))
    scan_text(added, "git history", findings)


def check_config(findings):
    for path, pattern, desc in CONFIG_RULES:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            # Comments may name a removed setting; only live config counts.
            live = "\n".join(l for l in fh if not l.lstrip().startswith(("#", "//")))
            if re.search(pattern, live):
                findings.append(f"{desc} in {path}")
    # Only the read-only socket proxy may mount the Docker socket.
    if os.path.exists("docker-compose.yml"):
        compose = open("docker-compose.yml", encoding="utf-8").read()
        for block in re.split(r"\n  (?=[a-z][\w-]*:\n)", compose):
            if "docker.sock" in block and "docker-socket-proxy" not in block:
                findings.append("Docker socket mounted outside docker-proxy in docker-compose.yml")


def main():
    findings = []
    scan_working_tree(findings)
    scan_git_history(findings)
    check_config(findings)
    if findings:
        for f in findings:
            print(f"[FAIL] {f}")
        print(f"{len(findings)} security issue(s) found. Fix them before committing.")
        sys.exit(1)
    print("[PASS] No exposed secrets in tree or history; stack configuration hardened.")


if __name__ == "__main__":
    main()
