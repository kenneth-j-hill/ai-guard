"""Tests for whole-file protection.

These tests document the behavior of protecting entire files from modification.
"""

import pytest
from pathlib import Path

from ai_guard.core import GuardFile, compute_file_hash


class TestWholeFileProtection:
    """Tests for protecting entire files."""

    def test_add_file_protection(self, temp_project):
        """Adding file protection creates an entry with the file's hash."""
        # Create a file to protect
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 'do-not-change'\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        added, skipped = guard.add_file("config.py")

        assert added is not None
        assert skipped is None
        assert added.path == "config.py"
        assert added.identifier is None
        assert len(added.hash) == 16  # SHA-256 truncated to 16 chars

    def test_file_protection_persists(self, temp_project):
        """File protection is saved to and loaded from .ai-guard file."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 'do-not-change'\n", encoding="utf-8")

        # Add protection and save
        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        # Load in a new instance
        guard2 = GuardFile(temp_project)
        entries = guard2.list_entries()

        # 2 entries: self-protection + config.py
        assert len(entries) == 2
        assert entries[0].path == ".ai-guard"  # Self-protection is first
        assert entries[1].path == "config.py"

    def test_verify_unchanged_file_passes(self, temp_project):
        """Verification passes when a protected file hasn't changed."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 'do-not-change'\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        failures = guard.verify()
        assert len(failures) == 0

    def test_verify_changed_file_fails(self, temp_project):
        """Verification fails when a protected file has been modified."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 'do-not-change'\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        # Modify the file
        filepath.write_text("SECRET = 'changed!'\n", encoding="utf-8")

        failures = guard.verify()
        assert len(failures) == 1
        assert failures[0][0].path == "config.py"
        assert failures[0][1] == "hash mismatch"

    def test_verify_deleted_file_fails(self, temp_project):
        """Verification fails when a protected file has been deleted."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 'do-not-change'\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        # Delete the file
        filepath.unlink()

        failures = guard.verify()
        assert len(failures) == 1
        assert failures[0][1] == "file not found"

    def test_update_file_hash(self, temp_project):
        """Updating recalculates the hash for intentional changes."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 'original'\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        original_hash = guard.entries[0].hash

        # Modify the file
        filepath.write_text("SECRET = 'updated'\n", encoding="utf-8")

        # Update the protection
        guard.update("config.py")
        new_hash = guard.entries[0].hash

        assert new_hash != original_hash
        assert guard.verify() == []  # Should pass now

    def test_remove_file_protection(self, temp_project):
        """Removing protection deletes the entry."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 'do-not-change'\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        assert len(guard.entries) == 1

        count = guard.remove("config.py")
        assert count == 1
        assert len(guard.entries) == 0

    def test_add_file_skips_existing(self, temp_project):
        """Adding a file that is already protected skips it."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 'do-not-change'\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        added, skipped = guard.add_file("config.py")
        assert added is not None
        assert skipped is None

        # Add again - should skip
        added2, skipped2 = guard.add_file("config.py")
        assert added2 is None
        assert skipped2 is not None
        assert skipped2.path == "config.py"

        # Only one entry should exist
        file_entries = [e for e in guard.entries if e.path == "config.py"]
        assert len(file_entries) == 1

    def test_path_normalization(self, temp_project):
        """Paths with backslashes are normalized to forward slashes."""
        filepath = temp_project / "subdir" / "config.py"
        filepath.parent.mkdir()
        filepath.write_text("SECRET = 'value'\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        # Use backslashes like Windows
        added, skipped = guard.add_file("subdir\\config.py")

        assert added.path == "subdir/config.py"


class TestSelfProtection:
    """Tests for automatic self-protection of the .ai-guard file."""

    def test_ai_guard_protects_itself(self, temp_project):
        """The .ai-guard file automatically includes self-protection."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        # Check that .ai-guard entry exists and is first
        entries = guard.list_entries()
        assert entries[0].path == ".ai-guard"
        assert entries[0].identifier is None

    def test_self_protection_verification_passes(self, temp_project):
        """Self-protection verification passes for unmodified .ai-guard."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        failures = guard.verify()
        assert len(failures) == 0

    def test_self_protection_detects_tampering(self, temp_project):
        """Self-protection detects when .ai-guard file is tampered with."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        # Tamper with the .ai-guard file by removing an entry
        ai_guard_path = temp_project / ".ai-guard"
        content = ai_guard_path.read_text()
        # Remove the config.py line
        lines = [l for l in content.splitlines() if "config.py" not in l]
        ai_guard_path.write_text("\n".join(lines) + "\n")

        # Reload and verify - should detect tampering
        guard2 = GuardFile(temp_project)
        failures = guard2.verify()

        # Should have a failure for .ai-guard hash mismatch
        assert len(failures) == 1
        assert failures[0][0].path == ".ai-guard"
        assert failures[0][1] == "hash mismatch"

    def test_self_protection_detects_added_entry(self, temp_project):
        """Self-protection detects when entries are added to .ai-guard."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        # Tamper by adding a fake entry
        ai_guard_path = temp_project / ".ai-guard"
        content = ai_guard_path.read_text()
        content += "fake/file.py:0000000000000000\n"
        ai_guard_path.write_text(content)

        # Reload and verify
        guard2 = GuardFile(temp_project)
        failures = guard2.verify()

        # Should detect tampering (hash mismatch) and fake file not found
        paths = [f[0].path for f in failures]
        assert ".ai-guard" in paths
