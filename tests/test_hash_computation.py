"""Tests for hash computation.

These tests document exactly what is included in hash calculations
for both files and identifiers.
"""

import pytest
from pathlib import Path

from ai_guard.core import compute_hash, compute_file_hash, compute_identifier_hash


class TestFileHashing:
    """Tests for whole-file hash computation."""

    def test_hash_is_deterministic(self, temp_project):
        """The same content always produces the same hash."""
        filepath = temp_project / "test.py"
        filepath.write_text("x = 1\n", encoding="utf-8")

        hash1 = compute_file_hash(filepath)
        hash2 = compute_file_hash(filepath)

        assert hash1 == hash2

    def test_different_content_different_hash(self, temp_project):
        """Different content produces different hashes."""
        filepath = temp_project / "test.py"

        filepath.write_text("x = 1\n", encoding="utf-8")
        hash1 = compute_file_hash(filepath)

        filepath.write_text("x = 2\n", encoding="utf-8")
        hash2 = compute_file_hash(filepath)

        assert hash1 != hash2

    def test_whitespace_matters(self, temp_project):
        """Changes in whitespace affect the hash."""
        filepath = temp_project / "test.py"

        filepath.write_text("x = 1\n", encoding="utf-8")
        hash1 = compute_file_hash(filepath)

        filepath.write_text("x  =  1\n", encoding="utf-8")  # Extra spaces
        hash2 = compute_file_hash(filepath)

        assert hash1 != hash2

    def test_hash_length(self, temp_project):
        """Hash is truncated to 16 characters."""
        filepath = temp_project / "test.py"
        filepath.write_text("content\n", encoding="utf-8")

        file_hash = compute_file_hash(filepath)
        assert len(file_hash) == 16


class TestIdentifierHashing:
    """Tests for identifier hash computation."""

    def test_function_body_included(self, temp_project):
        """Changing the function body changes the hash."""
        filepath = temp_project / "test.py"

        filepath.write_text("def func():\n    return 1\n", encoding="utf-8")
        hash1 = compute_identifier_hash(filepath, "func")

        filepath.write_text("def func():\n    return 2\n", encoding="utf-8")
        hash2 = compute_identifier_hash(filepath, "func")

        assert hash1 != hash2

    def test_function_signature_included(self, temp_project):
        """Changing the function signature changes the hash."""
        filepath = temp_project / "test.py"

        filepath.write_text("def func():\n    pass\n", encoding="utf-8")
        hash1 = compute_identifier_hash(filepath, "func")

        filepath.write_text("def func(x):\n    pass\n", encoding="utf-8")
        hash2 = compute_identifier_hash(filepath, "func")

        assert hash1 != hash2

    def test_docstring_included(self, temp_project):
        """Changing the docstring changes the hash."""
        filepath = temp_project / "test.py"

        filepath.write_text('def func():\n    """Original."""\n    pass\n', encoding="utf-8")
        hash1 = compute_identifier_hash(filepath, "func")

        filepath.write_text('def func():\n    """Modified."""\n    pass\n', encoding="utf-8")
        hash2 = compute_identifier_hash(filepath, "func")

        assert hash1 != hash2

    def test_decorator_included(self, temp_project):
        """Changing a decorator changes the hash."""
        filepath = temp_project / "test.py"

        filepath.write_text("@dec1\ndef func():\n    pass\n", encoding="utf-8")
        hash1 = compute_identifier_hash(filepath, "func")

        filepath.write_text("@dec2\ndef func():\n    pass\n", encoding="utf-8")
        hash2 = compute_identifier_hash(filepath, "func")

        assert hash1 != hash2

    def test_adding_decorator_changes_hash(self, temp_project):
        """Adding a decorator changes the hash."""
        filepath = temp_project / "test.py"

        filepath.write_text("def func():\n    pass\n", encoding="utf-8")
        hash1 = compute_identifier_hash(filepath, "func")

        filepath.write_text("@decorator\ndef func():\n    pass\n", encoding="utf-8")
        hash2 = compute_identifier_hash(filepath, "func")

        assert hash1 != hash2

    def test_class_body_included(self, temp_project):
        """Changing a class body changes the hash."""
        filepath = temp_project / "test.py"

        filepath.write_text("class Foo:\n    x = 1\n", encoding="utf-8")
        hash1 = compute_identifier_hash(filepath, "Foo")

        filepath.write_text("class Foo:\n    x = 2\n", encoding="utf-8")
        hash2 = compute_identifier_hash(filepath, "Foo")

        assert hash1 != hash2

    def test_class_method_change_changes_class_hash(self, temp_project):
        """Changing a method inside a class changes the class hash."""
        filepath = temp_project / "test.py"

        filepath.write_text("class Foo:\n    def method(self):\n        return 1\n", encoding="utf-8")
        hash1 = compute_identifier_hash(filepath, "Foo")

        filepath.write_text("class Foo:\n    def method(self):\n        return 2\n", encoding="utf-8")
        hash2 = compute_identifier_hash(filepath, "Foo")

        assert hash1 != hash2

    def test_nonexistent_identifier_returns_none(self, temp_project):
        """Requesting a nonexistent identifier returns None."""
        filepath = temp_project / "test.py"
        filepath.write_text("x = 1\n", encoding="utf-8")

        result = compute_identifier_hash(filepath, "nonexistent")
        assert result is None

    def test_unsupported_file_type_returns_none(self, temp_project):
        """Unsupported file types return None for identifier hashing."""
        filepath = temp_project / "test.txt"
        filepath.write_text("some text\n", encoding="utf-8")

        result = compute_identifier_hash(filepath, "anything")
        assert result is None
