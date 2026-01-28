"""Tests for identifier-level protection.

These tests document the behavior of protecting specific identifiers
(functions, classes, variables) within files.
"""

import pytest
from pathlib import Path

from ai_guard.core import GuardFile


class TestIdentifierProtection:
    """Tests for protecting specific identifiers."""

    def test_protect_function(self, temp_project, sample_python_file):
        """Protecting a function includes its entire definition."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "simple_function")

        assert len(entries) == 1
        assert entries[0].path == "sample.py"
        assert entries[0].identifier == "simple_function"
        assert len(entries[0].hash) == 16

    def test_protect_class(self, temp_project, sample_python_file):
        """Protecting a class includes the entire class body."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "SimpleClass")

        assert len(entries) == 1
        assert entries[0].identifier == "SimpleClass"

    def test_protect_async_function(self, temp_project, sample_python_file):
        """Async functions can be protected."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "async_function")

        assert len(entries) == 1
        assert entries[0].identifier == "async_function"

    def test_protect_module_constant(self, temp_project, sample_python_file):
        """Module-level constants can be protected."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "MODULE_CONSTANT")

        assert len(entries) == 1
        assert entries[0].identifier == "MODULE_CONSTANT"

    def test_protect_annotated_variable(self, temp_project, sample_python_file):
        """Annotated variables can be protected."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "annotated_var")

        assert len(entries) == 1
        assert entries[0].identifier == "annotated_var"

    def test_verify_unchanged_identifier_passes(self, temp_project, sample_python_file):
        """Verification passes when a protected identifier hasn't changed."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "simple_function")
        guard.save()

        failures = guard.verify()
        assert len(failures) == 0

    def test_verify_changed_identifier_fails(self, temp_project, sample_python_file):
        """Verification fails when a protected identifier has been modified."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "simple_function")
        guard.save()

        # Modify the function
        content = sample_python_file.read_text()
        content = content.replace("return 1", "return 2")
        sample_python_file.write_text(content)

        failures = guard.verify()
        assert len(failures) == 1
        assert failures[0][0].identifier == "simple_function"
        assert failures[0][1] == "hash mismatch"

    def test_verify_deleted_identifier_fails(self, temp_project, sample_python_file):
        """Verification fails when a protected identifier has been removed."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "simple_function")
        guard.save()

        # Remove the function
        content = sample_python_file.read_text()
        # Remove the entire function block
        lines = content.split("\n")
        new_lines = []
        skip = False
        for line in lines:
            if "def simple_function" in line:
                skip = True
                continue
            if skip and line and not line.startswith(" ") and not line.startswith("\t"):
                skip = False
            if not skip:
                new_lines.append(line)
        sample_python_file.write_text("\n".join(new_lines))

        failures = guard.verify()
        assert len(failures) == 1
        assert failures[0][1] == "identifier not found"

    def test_nonexistent_identifier_raises(self, temp_project, sample_python_file):
        """Adding protection for a nonexistent identifier raises an error."""
        guard = GuardFile(temp_project)

        with pytest.raises(ValueError, match="No identifiers matching"):
            guard.add_identifier("sample.py", "nonexistent_function")

    def test_remove_identifier_protection(self, temp_project, sample_python_file):
        """Removing identifier protection deletes only that entry."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "simple_function")
        guard.add_identifier("sample.py", "another_function")
        assert len(guard.entries) == 2

        count = guard.remove("sample.py", "simple_function")
        assert count == 1
        assert len(guard.entries) == 1
        assert guard.entries[0].identifier == "another_function"


class TestDecoratedIdentifiers:
    """Tests for identifiers with decorators."""

    def test_decorated_function_includes_decorator(self, temp_project, sample_python_file):
        """A decorated function's hash includes its decorator."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "decorated_function")
        original_hash = entries[0].hash

        # Modify the decorator
        content = sample_python_file.read_text()
        content = content.replace("@decorator\ndef decorated_function", "@other_decorator\ndef decorated_function")
        sample_python_file.write_text(content)

        guard2 = GuardFile(temp_project)
        guard2.add_identifier("sample.py", "decorated_function")
        new_hash = guard2.entries[0].hash

        assert original_hash != new_hash

    def test_multi_decorated_function(self, temp_project, sample_python_file):
        """Functions with multiple decorators include all decorators in hash."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "multi_decorated")
        original_hash = entries[0].hash

        # Remove one decorator
        content = sample_python_file.read_text()
        content = content.replace("@decorator_one\n@decorator_two", "@decorator_two")
        sample_python_file.write_text(content)

        guard2 = GuardFile(temp_project)
        guard2.add_identifier("sample.py", "multi_decorated")
        new_hash = guard2.entries[0].hash

        assert original_hash != new_hash


class TestClassMemberProtection:
    """Tests for protecting class members (methods, properties, class vars)."""

    def test_protect_class_method(self, temp_project, sample_python_file):
        """A method within a class can be protected using dot notation."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "SimpleClass.method")

        assert len(entries) == 1
        assert entries[0].path == "sample.py"
        assert entries[0].identifier == "SimpleClass.method"
        assert len(entries[0].hash) == 16

    def test_protect_decorated_method(self, temp_project, sample_python_file):
        """A decorated method includes its decorator in the hash."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "DecoratedClass.prop")

        assert len(entries) == 1
        assert entries[0].identifier == "DecoratedClass.prop"

    def test_protect_static_method(self, temp_project, sample_python_file):
        """Static methods can be protected."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "DecoratedClass.static_method")

        assert len(entries) == 1
        assert entries[0].identifier == "DecoratedClass.static_method"

    def test_verify_unchanged_method_passes(self, temp_project, sample_python_file):
        """Verification passes when a protected method hasn't changed."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "SimpleClass.method")
        guard.save()

        failures = guard.verify()
        assert len(failures) == 0

    def test_verify_changed_method_fails(self, temp_project, sample_python_file):
        """Verification fails when a protected method has been modified."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "SimpleClass.method")
        guard.save()

        # Modify the method
        content = sample_python_file.read_text()
        content = content.replace("return self", "return None")
        sample_python_file.write_text(content)

        failures = guard.verify()
        assert len(failures) == 1
        assert failures[0][0].identifier == "SimpleClass.method"
        assert failures[0][1] == "hash mismatch"

    def test_protect_all_class_members_with_wildcard(self, temp_project, sample_python_file):
        """Wildcard can protect all members of a class."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "DecoratedClass.*")

        # Should match prop and static_method
        assert len(entries) == 2
        names = {e.identifier for e in entries}
        assert "DecoratedClass.prop" in names
        assert "DecoratedClass.static_method" in names

    def test_protect_specific_members_with_wildcard(self, temp_project, sample_python_file):
        """Wildcard patterns filter class members."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "DecoratedClass.static_*")

        assert len(entries) == 1
        assert entries[0].identifier == "DecoratedClass.static_method"

    def test_nonexistent_class_member_raises(self, temp_project, sample_python_file):
        """Adding protection for a nonexistent class member raises an error."""
        guard = GuardFile(temp_project)

        with pytest.raises(ValueError, match="No identifiers matching"):
            guard.add_identifier("sample.py", "SimpleClass.nonexistent")

    def test_nonexistent_class_raises(self, temp_project, sample_python_file):
        """Adding protection for a nonexistent class raises an error."""
        guard = GuardFile(temp_project)

        with pytest.raises(ValueError, match="No identifiers matching"):
            guard.add_identifier("sample.py", "NonexistentClass.method")

    def test_decorated_method_hash_includes_decorator(self, temp_project, sample_python_file):
        """Changing a method's decorator changes its hash."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "DecoratedClass.prop")
        original_hash = entries[0].hash

        # Modify the decorator
        content = sample_python_file.read_text()
        content = content.replace("@property", "@cached_property")
        sample_python_file.write_text(content)

        guard2 = GuardFile(temp_project)
        guard2.add_identifier("sample.py", "DecoratedClass.prop")
        new_hash = guard2.entries[0].hash

        assert original_hash != new_hash
