"""Pluggable parser system for extracting identifiers from source code."""

from ai_guard.parsers.base import Parser, Identifier
from ai_guard.parsers.python import PythonParser

__all__ = ["Parser", "Identifier", "PythonParser"]
