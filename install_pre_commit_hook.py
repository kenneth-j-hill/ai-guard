#!/usr/bin/env python3
"""Install the ai-guard pre-commit hook."""

import subprocess
import sys


def main():
    result = subprocess.run([sys.executable, "-m", "ai_guard.cli", "install-hook"])
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
