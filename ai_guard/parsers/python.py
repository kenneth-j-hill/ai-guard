"""Python parser using the ast module."""

import ast
from typing import Optional

from ai_guard.parsers.base import Parser, Identifier, register_parser


class PythonParser(Parser):
    """Parser for Python source code using the built-in ast module.

    Extracts identifiers including:
    - Functions (def)
    - Async functions (async def)
    - Classes (class)
    - Module-level assignments (variables/constants)
    """

    def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
        """Extract a specific identifier from Python source code.

        Args:
            source: The full source code of the file.
            name: The name of the identifier to extract.

        Returns:
            An Identifier object if found, None otherwise.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        lines = source.splitlines(keepends=True)

        for node in ast.walk(tree):
            identifier = self._node_to_identifier(node, name, lines, source)
            if identifier:
                return identifier

        return None

    def list_identifiers(self, source: str) -> list[Identifier]:
        """List all top-level identifiers in Python source code.

        Args:
            source: The full source code of the file.

        Returns:
            A list of all identifiers found in the source.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        lines = source.splitlines(keepends=True)
        identifiers = []

        for node in ast.iter_child_nodes(tree):
            identifier = self._node_to_identifier(node, None, lines, source)
            if identifier:
                identifiers.append(identifier)

        return identifiers

    def _node_to_identifier(
        self,
        node: ast.AST,
        target_name: Optional[str],
        lines: list[str],
        source: str,
    ) -> Optional[Identifier]:
        """Convert an AST node to an Identifier if it matches.

        Args:
            node: The AST node to check.
            target_name: The name to match, or None to match any.
            lines: Source code split into lines.
            source: The full source code.

        Returns:
            An Identifier if the node matches, None otherwise.
        """
        name: Optional[str] = None
        start_line: int = 0
        end_line: int = 0

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            # Include decorators in the source
            if node.decorator_list:
                start_line = node.decorator_list[0].lineno
            else:
                start_line = node.lineno
            end_line = node.end_lineno or node.lineno

        elif isinstance(node, ast.Assign):
            # Module-level assignments like: x = 1, or x = y = 1
            # Use the first target's name
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    break
            if name:
                start_line = node.lineno
                end_line = node.end_lineno or node.lineno

        elif isinstance(node, ast.AnnAssign):
            # Annotated assignments like: x: int = 1
            if isinstance(node.target, ast.Name):
                name = node.target.id
                start_line = node.lineno
                end_line = node.end_lineno or node.lineno

        if name is None:
            return None

        if target_name is not None and name != target_name:
            return None

        # Extract the source code for this identifier
        # Lines are 1-indexed in AST
        identifier_source = "".join(lines[start_line - 1 : end_line])
        # Remove trailing newline if present
        identifier_source = identifier_source.rstrip("\n\r")

        return Identifier(
            name=name,
            source=identifier_source,
            start_line=start_line,
            end_line=end_line,
        )


# Register the Python parser for .py and .pyw files
register_parser([".py", ".pyw"], PythonParser)
