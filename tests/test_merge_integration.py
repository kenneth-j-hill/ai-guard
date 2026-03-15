"""End-to-end integration tests for merge workflows with real git repos.

These tests create real git repositories in pytest's tmp_path to test the
full merge -> resolve workflow.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ai_guard.cli import main
from ai_guard.core import GuardFile, compute_identifier_hash


_PROJECT_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git must be installed",
)


def _get_subprocess_env():
    """Get environment with PYTHONPATH set for subprocess to find ai_guard."""
    env = os.environ.copy()
    pythonpath = str(_PROJECT_ROOT)
    if "PYTHONPATH" in env:
        pythonpath = f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
    env["PYTHONPATH"] = pythonpath
    return env


def _git(cwd, *args):
    """Run a git command in a directory."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=_get_subprocess_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout


def _init_repo(path):
    """Initialize a git repo with initial commit."""
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "test@test.com")
    _git(path, "config", "user.name", "Test")
    # Create initial commit
    (path / "README.md").write_text("# test\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial")


@pytest.fixture
def git_project(tmp_path):
    """Create a real git repo with Python source files and ai-guard entries."""
    _init_repo(tmp_path)

    # Create source files
    (tmp_path / "module_a.py").write_text(
        "def func_a():\n    return 'original_a'\n\n"
        "def func_b():\n    return 'original_b'\n",
        encoding="utf-8",
    )
    (tmp_path / "module_b.py").write_text(
        "def func_c():\n    return 'original_c'\n",
        encoding="utf-8",
    )

    # Guard identifiers
    os.chdir(tmp_path)
    main(["add", "module_a.py:func_a"])
    main(["add", "module_a.py:func_b"])
    main(["add", "module_b.py:func_c"])

    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "add guarded code")

    return tmp_path


class TestMergeWithoutDriver:
    """Merge workflow without the merge driver installed."""

    def test_divergent_branches_resolve(self, git_project, monkeypatch):
        """Two branches modify different guarded identifiers, merge, resolve."""
        monkeypatch.chdir(git_project)

        # Branch A: modify func_a
        _git(git_project, "checkout", "-b", "branch-a")
        source = (git_project / "module_a.py").read_text(encoding="utf-8")
        source = source.replace("'original_a'", "'modified_by_a'")
        (git_project / "module_a.py").write_text(source, encoding="utf-8")
        main(["update", "module_a.py:func_a"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-a changes")

        # Branch B: modify func_b
        _git(git_project, "checkout", "main")
        _git(git_project, "checkout", "-b", "branch-b")
        source = (git_project / "module_a.py").read_text(encoding="utf-8")
        source = source.replace("'original_b'", "'modified_by_b'")
        (git_project / "module_a.py").write_text(source, encoding="utf-8")
        main(["update", "module_a.py:func_b"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-b changes")

        # Merge branch-a into branch-b
        try:
            _git(git_project, "merge", "branch-a")
        except RuntimeError:
            # .ai-guard has conflicts — that's what we're testing
            pass

        # Resolve
        result = main(["resolve"])
        assert result == 0

        # Verify passes
        result = main(["verify"])
        assert result == 0

    def test_both_modify_same_identifier(self, git_project, monkeypatch):
        """Both branches modify the same identifier, merge, resolve."""
        monkeypatch.chdir(git_project)

        # Branch A: modify func_a one way
        _git(git_project, "checkout", "-b", "branch-a")
        (git_project / "module_a.py").write_text(
            "def func_a():\n    return 'version_a'\n\n"
            "def func_b():\n    return 'original_b'\n",
            encoding="utf-8",
        )
        main(["update", "module_a.py:func_a"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-a changes")

        # Branch B: modify func_a differently
        _git(git_project, "checkout", "main")
        _git(git_project, "checkout", "-b", "branch-b")
        (git_project / "module_a.py").write_text(
            "def func_a():\n    return 'version_b'\n\n"
            "def func_b():\n    return 'original_b'\n",
            encoding="utf-8",
        )
        main(["update", "module_a.py:func_a"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-b changes")

        # Merge — will conflict on module_a.py source
        try:
            _git(git_project, "merge", "branch-a")
        except RuntimeError:
            pass

        # Resolve source conflict manually — pick branch-b's version
        (git_project / "module_a.py").write_text(
            "def func_a():\n    return 'version_b'\n\n"
            "def func_b():\n    return 'original_b'\n",
            encoding="utf-8",
        )

        # Resolve ai-guard
        result = main(["resolve"])
        assert result == 0

        # Verify — hash should match branch-b's version
        guard = GuardFile(git_project)
        func_a_entry = next(e for e in guard.entries if e.identifier == "func_a")
        expected = compute_identifier_hash(git_project / "module_a.py", "func_a")
        assert func_a_entry.hash == expected

    def test_deleted_file_dropped(self, git_project, monkeypatch):
        """An entry for a deleted file is dropped by resolve."""
        monkeypatch.chdir(git_project)

        # Branch A: delete module_b.py
        _git(git_project, "checkout", "-b", "branch-a")
        (git_project / "module_b.py").unlink()
        main(["update", "--all"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "delete module_b")

        # Branch B: modify func_a
        _git(git_project, "checkout", "main")
        _git(git_project, "checkout", "-b", "branch-b")
        source = (git_project / "module_a.py").read_text(encoding="utf-8")
        source = source.replace("'original_a'", "'modified'")
        (git_project / "module_a.py").write_text(source, encoding="utf-8")
        main(["update", "module_a.py:func_a"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-b changes")

        # Merge
        try:
            _git(git_project, "merge", "branch-a")
        except RuntimeError:
            pass

        result = main(["resolve"])
        assert result == 0

        guard = GuardFile(git_project)
        paths = {e.path for e in guard.entries}
        assert "module_b.py" not in paths

    def test_source_conflict_blocks_resolve(self, git_project, monkeypatch):
        """Resolve fails when guarded source files still have conflict markers."""
        monkeypatch.chdir(git_project)

        # Create conflicting changes to the same function on two branches
        _git(git_project, "checkout", "-b", "branch-a")
        (git_project / "module_a.py").write_text(
            "def func_a():\n    return 'version_a'\n\n"
            "def func_b():\n    return 'original_b'\n",
            encoding="utf-8",
        )
        main(["update", "module_a.py:func_a"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-a")

        _git(git_project, "checkout", "main")
        _git(git_project, "checkout", "-b", "branch-b")
        (git_project / "module_a.py").write_text(
            "def func_a():\n    return 'version_b'\n\n"
            "def func_b():\n    return 'original_b'\n",
            encoding="utf-8",
        )
        main(["update", "module_a.py:func_a"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-b")

        # Merge — will conflict
        try:
            _git(git_project, "merge", "branch-a")
        except RuntimeError:
            pass

        # Don't resolve source conflicts — try ai-guard resolve
        content = (git_project / "module_a.py").read_text(encoding="utf-8")
        if "<<<<<<<" in content:
            result = main(["resolve"])
            assert result == 1


class TestMergeWithDriver:
    """Merge workflow with the merge driver installed."""

    def _install_driver(self, git_project, monkeypatch):
        """Install git hooks with auto-yes."""
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])

    def test_driver_prevents_conflict_markers(self, git_project, monkeypatch):
        """With the merge driver, .ai-guard never gets conflict markers."""
        monkeypatch.chdir(git_project)
        self._install_driver(git_project, monkeypatch)

        # Branch A: modify func_a
        _git(git_project, "checkout", "-b", "branch-a")
        source = (git_project / "module_a.py").read_text(encoding="utf-8")
        source = source.replace("'original_a'", "'modified_by_a'")
        (git_project / "module_a.py").write_text(source, encoding="utf-8")
        main(["update", "module_a.py:func_a"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-a")

        # Branch B: modify func_b (different function, no source conflict)
        _git(git_project, "checkout", "main")
        _git(git_project, "checkout", "-b", "branch-b")
        self._install_driver(git_project, monkeypatch)
        source = (git_project / "module_a.py").read_text(encoding="utf-8")
        source = source.replace("'original_b'", "'modified_by_b'")
        (git_project / "module_a.py").write_text(source, encoding="utf-8")
        main(["update", "module_a.py:func_b"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-b")

        # Merge
        try:
            _git(git_project, "merge", "branch-a")
        except RuntimeError:
            pass  # Source may conflict but .ai-guard should not

        # Check .ai-guard has no conflict markers
        ai_guard_content = (git_project / ".ai-guard").read_text(encoding="utf-8")
        assert "<<<<<<<" not in ai_guard_content

    def test_driver_then_resolve(self, git_project, monkeypatch):
        """Full workflow: driver keeps entries, resolve recomputes hashes."""
        monkeypatch.chdir(git_project)
        self._install_driver(git_project, monkeypatch)

        # Branch A: add a new file and guard it
        _git(git_project, "checkout", "-b", "branch-a")
        (git_project / "new_a.py").write_text("def new_func_a():\n    return 1\n", encoding="utf-8")
        main(["add", "new_a.py:new_func_a"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-a adds new_a")

        # Branch B: add a different new file
        _git(git_project, "checkout", "main")
        _git(git_project, "checkout", "-b", "branch-b")
        self._install_driver(git_project, monkeypatch)
        (git_project / "new_b.py").write_text("def new_func_b():\n    return 2\n", encoding="utf-8")
        main(["add", "new_b.py:new_func_b"])
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-m", "branch-b adds new_b")

        # Merge
        _git(git_project, "merge", "branch-a")

        # Resolve
        result = main(["resolve"])
        assert result == 0

        # Both new entries should exist
        guard = GuardFile(git_project)
        identifiers = {e.identifier for e in guard.entries if e.identifier}
        assert "new_func_a" in identifiers
        assert "new_func_b" in identifiers

        # Verify passes
        result = main(["verify"])
        assert result == 0
