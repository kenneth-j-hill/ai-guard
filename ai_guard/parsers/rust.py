"""Rust parser using tree-sitter.

This parser extracts function, struct, enum, trait, impl, const, static,
type alias, macro, and module definitions from Rust source files.
"""

import fnmatch
from typing import Optional

from ai_guard.parsers.base import Parser, Identifier, register_parser

try:
    import tree_sitter_rust as _tsrust
    from tree_sitter import Language as _Language, Parser as _TSParser

    _RUST_LANGUAGE = _Language(_tsrust.language())
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    _TREE_SITTER_AVAILABLE = False

# Node types that represent top-level identifiers
_TOP_LEVEL_TYPES = {
    "function_item",
    "struct_item",
    "enum_item",
    "trait_item",
    "impl_item",
    "const_item",
    "static_item",
    "type_item",
    "macro_definition",
    "mod_item",
}


def _ensure_available() -> None:
    if not _TREE_SITTER_AVAILABLE:
        raise ImportError(
            "Rust support requires tree-sitter packages. "
            "Install them with: pip install ai-guard[rust]"
        )


def _make_parser() -> "_TSParser":
    _ensure_available()
    parser = _TSParser(_RUST_LANGUAGE)
    return parser


def _get_node_name(node) -> Optional[str]:
    """Get the name of a tree-sitter node.

    For most items this is the 'name' field. For impl_item it is
    the 'type' field (the type being implemented).
    """
    if node.type == "impl_item":
        type_node = node.child_by_field_name("type")
        return type_node.text.decode("utf-8") if type_node else None

    name_node = node.child_by_field_name("name")
    return name_node.text.decode("utf-8") if name_node else None


def _node_source(node, source_bytes: bytes) -> str:
    """Extract the source text for a node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")


class RustParser(Parser):
    """Parser for Rust source code using tree-sitter.

    Extracts identifiers including:
    - Functions (fn)
    - Structs (struct)
    - Enums (enum)
    - Traits (trait)
    - Impl blocks (impl) - named by the type they implement
    - Constants (const)
    - Statics (static)
    - Type aliases (type)
    - Macros (macro_rules!)
    - Modules (mod)
    - Struct fields and impl methods via :: notation
    """

    def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
        _ensure_available()
        source_bytes = source.encode("utf-8")
        tree = _make_parser().parse(source_bytes)
        root = tree.root_node

        # Check for :: member notation
        if "::" in name:
            return self._extract_member(root, source_bytes, name)

        for child in root.children:
            if child.type not in _TOP_LEVEL_TYPES:
                continue
            node_name = _get_node_name(child)
            if node_name == name:
                return self._node_to_identifier(child, source_bytes, name)

        return None

    def list_identifiers(self, source: str) -> list[Identifier]:
        _ensure_available()
        source_bytes = source.encode("utf-8")
        tree = _make_parser().parse(source_bytes)
        root = tree.root_node

        identifiers = []
        for child in root.children:
            if child.type not in _TOP_LEVEL_TYPES:
                continue
            node_name = _get_node_name(child)
            if node_name:
                ident = self._node_to_identifier(child, source_bytes, node_name)
                if ident:
                    identifiers.append(ident)

        return identifiers

    def expand_identifier_pattern(self, source: str, pattern: str) -> list[Identifier]:
        # Handle :: notation for struct fields / impl methods
        if "::" in pattern:
            _ensure_available()
            source_bytes = source.encode("utf-8")
            tree = _make_parser().parse(source_bytes)
            root = tree.root_node

            parts = pattern.split("::", 1)
            type_name, member_pattern = parts

            all_members = self._list_members(root, source_bytes, type_name)

            if "*" in member_pattern or "?" in member_pattern:
                full_pattern = f"{type_name}::{member_pattern}"
                return [m for m in all_members if fnmatch.fnmatch(m.name, full_pattern)]
            else:
                return [m for m in all_members if m.name == pattern]

        return super().expand_identifier_pattern(source, pattern)

    def _node_to_identifier(
        self, node, source_bytes: bytes, name: str
    ) -> Identifier:
        text = _node_source(node, source_bytes)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        return Identifier(
            name=name,
            source=text,
            start_line=start_line,
            end_line=end_line,
        )

    def _extract_member(
        self, root, source_bytes: bytes, qualified_name: str
    ) -> Optional[Identifier]:
        parts = qualified_name.split("::", 1)
        if len(parts) != 2:
            return None
        type_name, member_name = parts

        members = self._list_members(root, source_bytes, type_name)
        for m in members:
            if m.name == qualified_name:
                return m
        return None

    def _list_members(
        self, root, source_bytes: bytes, type_name: str
    ) -> list[Identifier]:
        """List all members of a type (struct fields + impl methods/consts)."""
        members = []
        seen_names = set()

        for child in root.children:
            # Struct/enum fields
            if child.type in ("struct_item", "enum_item"):
                node_name = _get_node_name(child)
                if node_name != type_name:
                    continue
                body = child.child_by_field_name("body")
                if not body:
                    continue
                for member in body.children:
                    if not member.is_named:
                        continue
                    if member.type == "field_declaration":
                        field_name_node = member.child_by_field_name("name")
                        if field_name_node:
                            fn = field_name_node.text.decode("utf-8")
                            qn = f"{type_name}::{fn}"
                            if qn not in seen_names:
                                seen_names.add(qn)
                                members.append(self._node_to_identifier(
                                    member, source_bytes, qn
                                ))
                    elif member.type == "enum_variant":
                        variant_name_node = member.child_by_field_name("name")
                        if variant_name_node:
                            vn = variant_name_node.text.decode("utf-8")
                            qn = f"{type_name}::{vn}"
                            if qn not in seen_names:
                                seen_names.add(qn)
                                members.append(self._node_to_identifier(
                                    member, source_bytes, qn
                                ))

            # Impl block methods/consts
            if child.type == "impl_item":
                impl_type = _get_node_name(child)
                if impl_type != type_name:
                    continue
                body = child.child_by_field_name("body")
                if not body:
                    continue
                for member in body.children:
                    if not member.is_named:
                        continue
                    member_name_node = member.child_by_field_name("name")
                    if member_name_node:
                        mn = member_name_node.text.decode("utf-8")
                        qn = f"{type_name}::{mn}"
                        if qn not in seen_names:
                            seen_names.add(qn)
                            members.append(self._node_to_identifier(
                                member, source_bytes, qn
                            ))

        return members


register_parser([".rs"], RustParser)
