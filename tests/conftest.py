"""Pytest fixtures for ai-guard tests."""

import pytest
from pathlib import Path
import tempfile
import shutil


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory with a .git folder.

    Yields:
        Path: The temporary project root directory.
    """
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    yield tmp_path


@pytest.fixture
def sample_python_file(temp_project):
    """Create a sample Python file with various identifiers.

    Returns:
        Path: Path to the created file.
    """
    source = '''"""Sample module for testing."""

MODULE_CONSTANT = 42

annotated_var: int = 100


def simple_function():
    """A simple function."""
    return 1


def another_function(x, y):
    """Function with parameters."""
    return x + y


@decorator
def decorated_function():
    """A decorated function."""
    pass


@decorator_one
@decorator_two
def multi_decorated():
    """Function with multiple decorators."""
    pass


async def async_function():
    """An async function."""
    await something()


class SimpleClass:
    """A simple class."""

    def method(self):
        return self


class DecoratedClass:
    """Class with decorators on methods."""

    @property
    def prop(self):
        return self._value

    @staticmethod
    def static_method():
        pass


def test_invariant_one():
    """First test invariant."""
    assert True


def test_invariant_two():
    """Second test invariant."""
    assert True


def test_invariant_three():
    """Third test invariant."""
    assert True


def test_other():
    """A test that doesn't match the invariant pattern."""
    pass
'''
    filepath = temp_project / "sample.py"
    filepath.write_text(source, encoding="utf-8")
    return filepath
