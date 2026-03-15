"""Core functionality for ai-guard."""

import fnmatch
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Conflict marker patterns (git 2-way and 3-way/diff3 styles)
_CONFLICT_MARKER_RE = re.compile(r'^(<{7}|={7}|>{7}|\|{7})\s', re.MULTILINE)


@dataclass
class ProtectedEntry:
    """A protected file or identifier entry."""

    path: str
    identifier: Optional[str]  # None for whole-file protection
    hash: str

    @property
    def is_self_protection(self) -> bool:
        """Whether this is the .ai-guard self-protection entry."""
        return self.path == ".ai-guard" and self.identifier is None

    def to_line(self) -> str:
        """Convert to a line in the .ai-guard file."""
        if self.identifier:
            return f"{self.path}:{self.identifier}:{self.hash}"
        return f"{self.path}:{self.hash}"

    @classmethod
    def from_line(cls, line: str) -> Optional["ProtectedEntry"]:
        """Parse a line from the .ai-guard file.

        Format:
            path/to/file.py:<hash>                    # whole file
            path/to/file.py:identifier:<hash>         # specific identifier
            path/to/file.h:Struct::member:<hash>      # C/C++ struct/class member

        Returns:
            ProtectedEntry if valid, None otherwise.
        """
        line = line.strip()
        if not line or line.startswith("#"):
            return None

        # The hash is always the last 16 hex characters after the final colon
        # Split from the right to handle identifiers containing colons (e.g., C++ ::)
        last_colon = line.rfind(":")
        if last_colon == -1:
            return None

        hash_part = line[last_colon + 1:]
        rest = line[:last_colon]

        # Now split the rest into path and optional identifier
        # The path is everything before the first colon that follows a file extension
        # For simplicity, find the first colon in rest
        first_colon = rest.find(":")
        if first_colon == -1:
            # Whole file: path:hash (but we already removed hash)
            # This means: rest = path
            return cls(path=normalize_path(rest), identifier=None, hash=hash_part)

        path = rest[:first_colon]
        identifier = rest[first_colon + 1:]

        if identifier:
            return cls(path=normalize_path(path), identifier=identifier, hash=hash_part)
        else:
            return cls(path=normalize_path(path), identifier=None, hash=hash_part)


def normalize_path(path: str) -> str:
    """Normalize path separators to forward slashes."""
    return path.replace("\\", "/")


def compute_hash(content: str) -> str:
    """Compute a SHA-256 hash of the content.

    Line endings are normalized (CR stripped) before hashing to ensure
    consistent hashes across Windows (CRLF) and Unix (LF) systems.

    Args:
        content: The content to hash.

    Returns:
        The first 16 characters of the hex digest.
    """
    normalized = content.replace('\r', '')
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def compute_file_hash(filepath: Path) -> str:
    """Compute a hash of a file's contents.

    Args:
        filepath: Path to the file.

    Returns:
        The hash of the file contents.
    """
    content = filepath.read_text(encoding="utf-8")
    return compute_hash(content)


def compute_identifier_hash(filepath: Path, identifier: str) -> Optional[str]:
    """Compute a hash of an identifier's source code.

    Args:
        filepath: Path to the file.
        identifier: Name of the identifier.

    Returns:
        The hash of the identifier's source, or None if not found.
    """
    from ai_guard.parsers.base import get_parser_for_file

    parser = get_parser_for_file(str(filepath))
    if not parser:
        return None

    source = filepath.read_text(encoding="utf-8")
    ident = parser.extract_identifier(source, identifier)
    if not ident:
        return None

    return compute_hash(ident.source)


class GuardFile:
    """Manages the .ai-guard file."""

    def __init__(self, root: Path):
        """Initialize with the project root directory.

        Args:
            root: The project root directory.
        """
        self.root = root
        self.filepath = root / ".ai-guard"
        self.entries: list[ProtectedEntry] = []
        self.has_conflicts: bool = False
        self._load()

    def _load(self) -> None:
        """Load entries from the .ai-guard file."""
        self.entries = []
        self.has_conflicts = False
        if not self.filepath.exists():
            return

        content = self.filepath.read_text(encoding="utf-8")
        if _CONFLICT_MARKER_RE.search(content):
            self.has_conflicts = True

        for line in content.splitlines():
            entry = ProtectedEntry.from_line(line)
            if entry:
                self.entries.append(entry)

    def save(self) -> None:
        """Save entries to the .ai-guard file.

        Automatically adds self-protection for the .ai-guard file itself.
        This prevents rogue modifications to the protection list.
        """
        # Ensure .ai-guard protects itself
        self._ensure_self_protection()

        # Build content excluding self-protection line for hash computation
        other_entries = [e for e in self.entries if not e.is_self_protection]
        other_lines = [entry.to_line() for entry in other_entries]
        content_to_hash = "\n".join(other_lines) + "\n" if other_lines else ""

        # Compute hash of the protected entries (excluding self-protection)
        self_hash = compute_hash(content_to_hash)

        # Update the self-protection entry with the computed hash
        for i, entry in enumerate(self.entries):
            if entry.is_self_protection:
                self.entries[i] = ProtectedEntry(
                    path=".ai-guard", identifier=None, hash=self_hash
                )
                break

        # Write the complete file
        lines = [entry.to_line() for entry in self.entries]
        self.filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _ensure_self_protection(self) -> None:
        """Ensure .ai-guard file is in the protection list."""
        for entry in self.entries:
            if entry.is_self_protection:
                return

        # Add self-protection entry with placeholder hash (will be computed in save())
        entry = ProtectedEntry(path=".ai-guard", identifier=None, hash="0" * 16)
        self.entries.insert(0, entry)  # Put it first

    def add_file(self, path: str) -> tuple[Optional[ProtectedEntry], Optional[ProtectedEntry]]:
        """Add whole-file protection.

        Args:
            path: Path to the file (relative to root).

        Returns:
            Tuple of (added, skipped). If the entry already exists, added is
            None and skipped is the existing entry. Otherwise, added is the
            new entry and skipped is None.
        """
        normalized = normalize_path(path)
        filepath = self.root / normalized
        file_hash = compute_file_hash(filepath)

        # Check for existing entry
        for entry in self.entries:
            if entry.path == normalized and entry.identifier is None:
                return None, entry

        entry = ProtectedEntry(path=normalized, identifier=None, hash=file_hash)
        self.entries.append(entry)
        return entry, None

    def add_identifier(self, path: str, identifier: str) -> tuple[list[ProtectedEntry], list[ProtectedEntry]]:
        """Add identifier protection, supporting wildcards.

        Args:
            path: Path to the file (relative to root).
            identifier: Name of the identifier (supports wildcards like test_*).
                        For nested identifiers (e.g., class members), the syntax
                        depends on the language parser (e.g., Class.method for Python).

        Returns:
            Tuple of (added, skipped) lists. Existing entries are skipped
            rather than overwritten.
        """
        from ai_guard.parsers.base import get_parser_for_file

        normalized = normalize_path(path)
        filepath = self.root / normalized

        parser = get_parser_for_file(str(filepath))
        if not parser:
            raise ValueError(f"No parser available for {filepath}")

        source = filepath.read_text(encoding="utf-8")

        # Let the parser expand the identifier pattern to a list of identifiers.
        # This allows each parser to handle nested identifiers (e.g., class members)
        # using language-appropriate syntax.
        all_identifiers = parser.expand_identifier_pattern(source, identifier)

        if not all_identifiers:
            raise ValueError(f"No identifiers matching '{identifier}' found in {path}")

        added = []
        skipped = []
        for ident in all_identifiers:
            # Check for existing entry
            existing = next(
                (e for e in self.entries
                 if e.path == normalized and e.identifier == ident.name),
                None,
            )
            if existing:
                skipped.append(existing)
                continue

            ident_hash = compute_hash(ident.source)
            entry = ProtectedEntry(
                path=normalized, identifier=ident.name, hash=ident_hash
            )
            self.entries.append(entry)
            added.append(entry)

        return added, skipped

    def update(self, path: str, identifier: Optional[str] = None) -> list[ProtectedEntry]:
        """Update the hash for a protected entry.

        Removes existing entries first, then re-adds them with fresh hashes.

        Args:
            path: Path to the file.
            identifier: Optional identifier name (supports wildcards).

        Returns:
            List of updated ProtectedEntry objects.
        """
        normalized = normalize_path(path)

        if identifier:
            # Remove matching entries before re-adding
            from ai_guard.parsers.base import get_parser_for_file

            parser = get_parser_for_file(str(self.root / normalized))
            if parser:
                source = (self.root / normalized).read_text(encoding="utf-8")
                all_identifiers = parser.expand_identifier_pattern(source, identifier)
                for ident in all_identifiers:
                    self.entries = [
                        e for e in self.entries
                        if not (e.path == normalized and e.identifier == ident.name)
                    ]
            added, _ = self.add_identifier(path, identifier)
            return added
        else:
            # Remove existing whole-file entry before re-adding
            self.entries = [e for e in self.entries if e.path != normalized or e.identifier]
            added, _ = self.add_file(path)
            return [added]

    def remove(self, path: str, identifier: Optional[str] = None) -> list[ProtectedEntry]:
        """Remove protection for a file or identifier.

        Args:
            path: Path to the file.
            identifier: Optional identifier name.

        Returns:
            List of removed entries.
        """
        normalized = normalize_path(path)

        if identifier:
            removed = [e for e in self.entries if e.path == normalized and e.identifier == identifier]
            self.entries = [e for e in self.entries if e not in removed]
        else:
            removed = [e for e in self.entries if e.path == normalized and not e.identifier]
            self.entries = [e for e in self.entries if e not in removed]

        return removed

    def verify(self) -> list[tuple[ProtectedEntry, str]]:
        """Verify all protected entries.

        Returns:
            List of (entry, reason) tuples for entries that failed verification.
        """
        failures = []

        for entry in self.entries:
            filepath = self.root / entry.path

            if not filepath.exists():
                failures.append((entry, "file not found"))
                continue

            if entry.identifier:
                current_hash = compute_identifier_hash(filepath, entry.identifier)
                if current_hash is None:
                    failures.append((entry, "identifier not found"))
                elif current_hash != entry.hash:
                    failures.append((entry, "hash mismatch"))
            elif entry.is_self_protection:
                current_hash = self._compute_self_protection_hash()
                if current_hash != entry.hash:
                    failures.append((entry, "hash mismatch"))
            else:
                current_hash = compute_file_hash(filepath)
                if current_hash != entry.hash:
                    failures.append((entry, "hash mismatch"))

        return failures

    def _compute_self_protection_hash(self) -> str:
        """Compute the hash for self-protection verification.

        The hash is computed over all entries except the self-protection entry,
        based on the actual file on disk (not in-memory entries).
        """
        if not self.filepath.exists():
            return ""

        # Read entries from disk
        disk_entries = []
        for line in self.filepath.read_text(encoding="utf-8").splitlines():
            entry = ProtectedEntry.from_line(line)
            if entry:
                disk_entries.append(entry)

        other_entries = [e for e in disk_entries if not e.is_self_protection]
        other_lines = [entry.to_line() for entry in other_entries]
        content_to_hash = "\n".join(other_lines) + "\n" if other_lines else ""
        return compute_hash(content_to_hash)

    def resolve(self) -> tuple[list[ProtectedEntry], list[str]]:
        """Resolve .ai-guard after a merge.

        Parses all entries (including those inside conflict marker regions),
        deduplicates by target, and recomputes hashes from the working tree.
        Entries whose files or identifiers no longer exist are dropped.

        Because the user performed the merge and resolved source conflicts,
        running resolve treats the merged source as approved.

        Returns:
            Tuple of (resolved_entries, conflicted_files).
            If conflicted_files is non-empty, resolution was blocked because
            guarded source files still contain merge conflict markers.
        """
        # Parse all entries from raw content, stripping conflict markers
        raw_entries = self._parse_all_entries()

        # Find unique guarded source files (files with identifier entries)
        guarded_files: set[str] = set()
        for entry in raw_entries:
            if entry.identifier and entry.path != ".ai-guard":
                guarded_files.add(entry.path)

        # Check guarded files for conflict markers
        conflicted_files = []
        for path in sorted(guarded_files):
            filepath = self.root / path
            if filepath.exists():
                content = filepath.read_text(encoding="utf-8")
                if _CONFLICT_MARKER_RE.search(content):
                    conflicted_files.append(path)

        if conflicted_files:
            return [], conflicted_files

        # Deduplicate by target (path + identifier)
        seen: dict[tuple[str, Optional[str]], ProtectedEntry] = {}
        for entry in raw_entries:
            key = (entry.path, entry.identifier)
            if key not in seen:
                seen[key] = entry
            # Duplicates are fine — we'll recompute anyway

        # Recompute hashes from working tree
        resolved = []
        for (path, identifier), entry in seen.items():
            if entry.is_self_protection:
                continue  # Self-protection is handled by save()

            filepath = self.root / path
            if not filepath.exists():
                continue  # File gone — drop entry

            if identifier:
                new_hash = compute_identifier_hash(filepath, identifier)
                if new_hash is None:
                    continue  # Identifier gone — drop entry
                resolved.append(ProtectedEntry(path=path, identifier=identifier, hash=new_hash))
            else:
                new_hash = compute_file_hash(filepath)
                resolved.append(ProtectedEntry(path=path, identifier=None, hash=new_hash))

        self.entries = resolved
        self.has_conflicts = False
        return resolved, []

    def _parse_all_entries(self) -> list[ProtectedEntry]:
        """Parse all entries from .ai-guard, stripping conflict markers.

        Handles both clean files and files with 2-way or 3-way (diff3)
        conflict markers.
        """
        if not self.filepath.exists():
            return []

        entries = []
        for line in self.filepath.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            # Skip conflict marker lines
            if (stripped.startswith("<<<<<<<") or
                    stripped.startswith("=======") or
                    stripped.startswith(">>>>>>>") or
                    stripped.startswith("|||||||")):
                continue
            entry = ProtectedEntry.from_line(line)
            if entry:
                entries.append(entry)
        return entries

    def list_entries(self) -> list[ProtectedEntry]:
        """List all protected entries.

        Returns:
            List of all ProtectedEntry objects.
        """
        return list(self.entries)
