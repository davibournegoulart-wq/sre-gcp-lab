#!/usr/bin/env python3
"""
Security & Credential Linter for SRE GCP Lab.
Scans for accidental API keys, private certificates, and insecure configurations.
"""

import os
import re
import sys

PATTERNS = [
    (r"AIza[0-9A-Za-z-_]{35}", "Google API Key"),
    (r"-----BEGIN (RSA|EC|DSA|OPENSSH|PRIVATE)? KEY-----", "Private Key"),
    (r"ghp_[0-9a-zA-Z]{36}", "GitHub Personal Access Token"),
    (r"xox[baprs]-[0-9a-zA-Z]{10,48}", "Slack Token"),
    (r"ey[A-Za-z0-9_-]{10,}\.ey[A-Za-z0-9_-]{10,}\.", "Raw JWT Token"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID")
]

IGNORE_DIRS = {".git", ".terraform", "node_modules", "__pycache__", ".venv"}


def scan_repo():
    clean = True
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            file_path = os.path.join(root, f)
            if f in ["security-check.py", ".gitignore"]:
                continue
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                    for pattern, desc in PATTERNS:
                        if re.search(pattern, content):
                            print(f"❌ [SECURITY VIOLATION] Detected {desc} in: {file_path}")
                            clean = False
            except Exception as e:
                print(f"⚠️ Could not inspect {file_path}: {e}")

    if clean:
        print("✅ [SECURITY PASSED] Zero exposed secrets, credentials or private keys found.")
        sys.exit(0)
    else:
        print("🚨 Secrets detected! Please remove them before committing to Git.")
        sys.exit(1)


if __name__ == "__main__":
    scan_repo()

