"""Pluggable parser system for extracting identifiers from source code."""

from ai_guard.parsers.base import Parser, Identifier
from ai_guard.parsers.python import PythonParser
from ai_guard.parsers.gcc import GCCParser, GPPParser

__all__ = ["Parser", "Identifier", "PythonParser", "GCCParser", "GPPParser"]
