"""Python parser using the ast module."""

import ast
import fnmatch
from typing import Optional

from ai_guard.parsers.base import Parser, Identifier, register_parser


class PythonParser(Parser):
    """Parser for Python source code using the built-in ast module.

    Extracts identifiers including:
    - Functions (def)
    - Async functions (async def)
    - Classes (class)
    - Module-level assignments (variables/constants)
    - Class members (methods, properties, class variables) via dot notation
    """

    def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
        """Extract a specific identifier from Python source code.

        Args:
            source: The full source code of the file.
            name: The name of the identifier to extract. Can be a simple name
                  like "func" or a dotted name like "ClassName.method".

        Returns:
            An Identifier object if found, None otherwise.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        lines = source.splitlines(keepends=True)

        # Check for dotted name (class member)
        if "." in name:
            return self._extract_class_member(tree, name, lines)

        for node in ast.walk(tree):
            identifier = self._node_to_identifier(node, name, lines)
            if identifier:
                return identifier

        return None

    def _extract_class_member(
        self,
        tree: ast.Module,
        dotted_name: str,
        lines: list[str],
    ) -> Optional[Identifier]:
        """Extract a class member using dotted notation.

        Args:
            tree: The parsed AST.
            dotted_name: Name in format "ClassName.member_name".
            lines: Source code split into lines.

        Returns:
            An Identifier if found, None otherwise.
        """
        parts = dotted_name.split(".", 1)
        if len(parts) != 2:
            return None
        class_name, member_name = parts

        # Find the class
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                # Search within the class body
                for member in node.body:
                    identifier = self._node_to_identifier(
                        member, member_name, lines, qualified_name=dotted_name
                    )
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
            identifier = self._node_to_identifier(node, None, lines)
            if identifier:
                identifiers.append(identifier)

        return identifiers

    def list_class_members(self, source: str, class_name: str) -> list[Identifier]:
        """List all members of a specific class.

        Args:
            source: The full source code of the file.
            class_name: Name of the class to list members for.

        Returns:
            A list of all identifiers (methods, properties, class vars) in the class.
            Names are qualified with the class name (e.g., "ClassName.method").
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        lines = source.splitlines(keepends=True)
        identifiers = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for member in node.body:
                    qualified_name = f"{class_name}.{self._get_node_name(member)}"
                    if self._get_node_name(member):
                        identifier = self._node_to_identifier(
                            member, None, lines, qualified_name=qualified_name
                        )
                        if identifier:
                            identifiers.append(identifier)
                break

        return identifiers

    def _get_node_name(self, node: ast.AST) -> Optional[str]:
        """Get the name of an AST node if it has one."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return node.name
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    return target.id
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                return node.target.id
        return None

    def expand_identifier_pattern(self, source: str, pattern: str) -> list[Identifier]:
        """Expand an identifier pattern to matching identifiers.

        Supports Python-specific dot notation for class members:
        - "MyClass.method" - specific class member
        - "MyClass.*" - all members of a class
        - "MyClass.test_*" - members matching a pattern

        Args:
            source: The full source code of the file.
            pattern: The identifier pattern, possibly with wildcards or dot notation.

        Returns:
            A list of matching Identifier objects.
        """
        # Check for Python class member notation (contains a dot)
        if "." in pattern:
            parts = pattern.split(".", 1)
            class_name, member_pattern = parts

            # Get all members of the class
            all_members = self.list_class_members(source, class_name)

            # Filter by member pattern (which may include wildcards)
            if "*" in member_pattern or "?" in member_pattern:
                full_pattern = f"{class_name}.{member_pattern}"
                return [m for m in all_members if fnmatch.fnmatch(m.name, full_pattern)]
            else:
                return [m for m in all_members if m.name == pattern]

        # Fall back to base implementation for top-level identifiers
        return super().expand_identifier_pattern(source, pattern)

    def _node_to_identifier(
        self,
        node: ast.AST,
        target_name: Optional[str],
        lines: list[str],
        qualified_name: Optional[str] = None,
    ) -> Optional[Identifier]:
        """Convert an AST node to an Identifier if it matches.

        Args:
            node: The AST node to check.
            target_name: The name to match, or None to match any.
            lines: Source code split into lines.
            qualified_name: If provided, use this as the identifier name instead
                           of the node's name. Used for class members.

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

        # Use qualified name if provided (for class members)
        output_name = qualified_name if qualified_name else name

        return Identifier(
            name=output_name,
            source=identifier_source,
            start_line=start_line,
            end_line=end_line,
        )


# Register the Python parser for .py and .pyw files
register_parser([".py", ".pyw"], PythonParser)
