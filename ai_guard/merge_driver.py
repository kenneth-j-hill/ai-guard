"""Union merge driver for .ai-guard files.

This module implements the merge logic used by the git merge driver installed
by 'ai-guard install-git-hooks'. It performs a union merge: all entries from
both sides are kept. Same target with same hash is deduplicated; same target
with different hashes produces two entries (the post-merge hook runs
'ai-guard resolve' to pick the correct one).
"""

from pathlib import Path
from typing import Optional

from ai_guard.core import ProtectedEntry


def parse_entries(filepath: Path) -> list[ProtectedEntry]:
    """Parse entries from an .ai-guard file.

    Args:
        filepath: Path to the file.

    Returns:
        List of parsed entries.
    """
    if not filepath.exists():
        return []

    entries = []
    for line in filepath.read_text(encoding="utf-8").splitlines():
        entry = ProtectedEntry.from_line(line)
        if entry:
            entries.append(entry)
    return entries


def union_merge(ours: list[ProtectedEntry], theirs: list[ProtectedEntry]) -> list[ProtectedEntry]:
    """Merge two entry lists, keeping all entries from both sides.

    - Same target and hash → deduplicated (keep one)
    - Same target, different hash → keep both
    - Entry only on one side → keep it

    Args:
        ours: Entries from the current branch.
        theirs: Entries from the other branch.

    Returns:
        Merged list of entries.
    """
    # Filter out .ai-guard self-protection entries — save() recomputes this.
    # Without this, each branch's different self-protection hash produces
    # duplicate .ai-guard lines in the merged output.
    def is_self_protection(e: ProtectedEntry) -> bool:
        return e.path == ".ai-guard" and e.identifier is None

    # Track what we already have by (path, identifier, hash)
    seen: set[tuple[str, Optional[str], str]] = set()
    result: list[ProtectedEntry] = []

    for entry in ours:
        if is_self_protection(entry):
            continue
        key = (entry.path, entry.identifier, entry.hash)
        if key not in seen:
            seen.add(key)
            result.append(entry)

    for entry in theirs:
        if is_self_protection(entry):
            continue
        key = (entry.path, entry.identifier, entry.hash)
        if key not in seen:
            seen.add(key)
            result.append(entry)

    return result


def run_merge_driver(ancestor_path: str, ours_path: str, theirs_path: str) -> int:
    """Run the merge driver.

    Git calls this with %O (ancestor), %A (ours), %B (theirs).
    The result is written to %A (ours_path).

    Args:
        ancestor_path: Path to the common ancestor version.
        ours_path: Path to the current branch version (result written here).
        theirs_path: Path to the other branch version.

    Returns:
        0 on success (always succeeds).
    """
    ours = parse_entries(Path(ours_path))
    theirs = parse_entries(Path(theirs_path))

    merged = union_merge(ours, theirs)

    lines = [entry.to_line() for entry in merged]
    Path(ours_path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0
