"""Integration tests that exercise the pre-commit hook end-to-end.

These tests verify that the hook actually blocks commits when protected
code is modified, and allows commits when it's restored.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from ai_guard.cli import main


class TestPreCommitHookIntegration:
    """Integration tests for the pre-commit hook."""

    def test_hook_fails_on_modified_protected_code(self, temp_project, sample_python_file, monkeypatch):
        """The pre-commit hook script fails when protected code is modified."""
        monkeypatch.chdir(temp_project)

        # Protect a test class
        main(["add", "sample.py:SimpleClass"])

        # Install the hook
        main(["install-hook"])

        hook_path = temp_project / ".git" / "hooks" / "pre-commit"
        original_content = sample_python_file.read_text()

        # Modify the protected code
        modified_content = original_content.replace(
            "class SimpleClass:",
            "class SimpleClass:  # modified"
        )
        sample_python_file.write_text(modified_content)

        # Run the hook script directly
        result = subprocess.run(
            [sys.executable, "-m", "ai_guard.cli", "verify"],
            capture_output=True,
            text=True,
        )

        # Hook should fail
        assert result.returncode == 1
        assert "hash mismatch" in result.stderr

        # Restore the original content
        sample_python_file.write_text(original_content)

        # Run the hook again
        result = subprocess.run(
            [sys.executable, "-m", "ai_guard.cli", "verify"],
            capture_output=True,
            text=True,
        )

        # Hook should pass now
        assert result.returncode == 0
        assert "verified successfully" in result.stdout

    def test_hook_script_execution(self, temp_project, sample_python_file, monkeypatch):
        """The actual hook shell script executes correctly."""
        monkeypatch.chdir(temp_project)

        # Protect a function
        main(["add", "sample.py:simple_function"])

        # Install the hook
        main(["install-hook"])

        hook_path = temp_project / ".git" / "hooks" / "pre-commit"
        original_content = sample_python_file.read_text()

        # Modify the protected function
        modified_content = original_content.replace(
            "return 1",
            "return 999"
        )
        sample_python_file.write_text(modified_content)

        # Run the actual hook script
        result = subprocess.run(
            ["sh", str(hook_path)],
            capture_output=True,
            text=True,
            cwd=temp_project,
        )

        # Hook script should exit with 1
        assert result.returncode == 1
        assert "Commit blocked" in result.stdout or "hash mismatch" in result.stderr

        # Restore
        sample_python_file.write_text(original_content)

        # Run hook again
        result = subprocess.run(
            ["sh", str(hook_path)],
            capture_output=True,
            text=True,
            cwd=temp_project,
        )

        # Should pass
        assert result.returncode == 0
