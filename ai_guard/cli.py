"""Command-line interface for ai-guard."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from ai_guard.core import GuardFile


# Module-level flags, set by main() before dispatching to commands.
_quiet = False
_porcelain = False


def qprint(*args, **kwargs) -> None:
    """Print to stdout unless quiet mode is active."""
    if not _quiet:
        print(*args, **kwargs)


def pprint(line: str) -> None:
    """Print a porcelain-format line (only when porcelain mode is active)."""
    if _porcelain:
        print(line)


def entry_target(entry) -> str:
    """Format an entry as a bare target string for porcelain output."""
    return f"{entry.path}:{entry.identifier}" if entry.identifier else entry.path


def _check_conflicts(guard: GuardFile) -> bool:
    """Check if .ai-guard has conflict markers. Print error and return True if so."""
    if guard.has_conflicts:
        print(
            "Error: .ai-guard contains merge conflict markers.\n"
            "Run 'ai-guard resolve' to recompute hashes from the merged source tree.",
            file=sys.stderr,
        )
        return True
    return False


def find_project_root(start: Optional[Path] = None) -> Path:
    """Find the project root by looking for .git directory.

    Args:
        start: Directory to start searching from. Defaults to cwd.

    Returns:
        The project root directory.
    """
    if start is None:
        start = Path.cwd()
    current = start.resolve()

    # Check current directory first
    if (current / ".git").exists():
        return current

    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    # Fall back to current directory
    return start.resolve()


def parse_target(target: str) -> tuple[str, Optional[str]]:
    """Parse a target string into path and optional identifier.

    Args:
        target: Target in format 'path/to/file.py' or 'path/to/file.py:identifier'

    Returns:
        Tuple of (path, identifier or None)

    Note:
        Colons in filenames are not supported (they're invalid on Windows anyway).
        The colon is used as delimiter between path and identifier.
    """
    if ":" not in target:
        return target, None

    # Look for known file extensions followed by colon, or glob patterns ending
    # in a known extension followed by colon (e.g., "*.py:" or "test_*.py:")
    import re
    extensions = r"\.(?:py|pyw|js|jsx|ts|tsx|cpp|c|h|hpp|cc|cxx|hxx|rs)"
    # Match extension (possibly followed by glob chars) then colon
    match = re.search(rf"({extensions}):", target)
    if match:
        idx = match.end() - 1  # Position of the colon
        path = target[:idx]
        identifier = target[idx + 1:]
        return path, identifier if identifier else None

    # Fallback: if path part looks like a glob pattern (contains * or ?),
    # split on the last colon
    if "*" in target or "?" in target:
        idx = target.rfind(":")
        path = target[:idx]
        identifier = target[idx + 1:]
        return path, identifier if identifier else None

    return target, None


def expand_glob_target(root: Path, target: str) -> list[tuple[str, Optional[str]]]:
    """Expand a target with glob patterns in the path.

    Args:
        root: Project root directory.
        target: Target like 'tests/*.py:func' or 'src/**/*.py'

    Returns:
        List of (path, identifier) tuples for each matching file.
    """
    import glob

    path, identifier = parse_target(target)

    # Check if path contains glob characters
    if "*" not in path and "?" not in path:
        return [(path, identifier)]

    # Expand the glob relative to root
    full_pattern = str(root / path)
    matches = glob.glob(full_pattern, recursive=True)

    if not matches:
        return [(path, identifier)]  # Return as-is, will error later

    # Convert back to relative paths
    results = []
    for match in sorted(matches):
        rel_path = str(Path(match).relative_to(root))
        # Normalize to forward slashes
        rel_path = rel_path.replace("\\", "/")
        results.append((rel_path, identifier))

    return results


def cmd_add(args: argparse.Namespace) -> int:
    """Add protection for a file or identifier."""
    root = find_project_root()
    guard = GuardFile(root)
    if _check_conflicts(guard):
        return 1

    any_success = False
    any_error = False

    for target in args.targets:
        for path, identifier in expand_glob_target(root, target):
            try:
                if identifier:
                    added, skipped = guard.add_identifier(path, identifier)
                    for entry in added:
                        qprint(f"Protected {entry.path}:{entry.identifier} ({entry.hash})")
                        pprint(entry_target(entry))
                        any_success = True
                    for entry in skipped:
                        qprint(f"Already protected: {entry.path}:{entry.identifier} ({entry.hash})")
                else:
                    added, skipped = guard.add_file(path)
                    if added:
                        qprint(f"Protected {added.path} ({added.hash})")
                        pprint(entry_target(added))
                        any_success = True
                    if skipped:
                        qprint(f"Already protected: {skipped.path} ({skipped.hash})")
            except FileNotFoundError:
                print(f"Error: File not found: {path}", file=sys.stderr)
                any_error = True
            except ImportError as e:
                print(f"Error: {e}", file=sys.stderr)
                any_error = True
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                any_error = True

    if any_success:
        guard.save()

    return 1 if any_error and not any_success else 0


def cmd_update(args: argparse.Namespace) -> int:
    """Update the hash for a protected entry."""
    if args.all and args.targets:
        print("Error: Cannot use --all with specific targets", file=sys.stderr)
        return 1
    if not args.all and not args.targets:
        print("Error: Must specify targets or use --all", file=sys.stderr)
        return 1

    root = find_project_root()
    guard = GuardFile(root)
    if _check_conflicts(guard):
        return 1

    any_success = False
    any_error = False

    if args.all:
        # Update all existing entries
        existing_entries = guard.list_entries()
        if not existing_entries:
            qprint("No protected entries to update")
            return 0

        for entry in existing_entries:
            # Skip self-protection entry - it's computed automatically
            if entry.path == ".ai-guard" and entry.identifier is None:
                continue

            old_hash = entry.hash
            try:
                updated = guard.update(entry.path, entry.identifier)
                for upd in updated:
                    if upd.hash != old_hash:
                        if upd.identifier:
                            qprint(f"Updated {upd.path}:{upd.identifier} ({upd.hash})")
                        else:
                            qprint(f"Updated {upd.path} ({upd.hash})")
                        pprint(entry_target(upd))
                    any_success = True
            except FileNotFoundError:
                target = entry_target(entry)
                print(f"Error: File not found: {target}", file=sys.stderr)
                print(f"  Run 'ai-guard remove {target}' to remove this entry.", file=sys.stderr)
                any_error = True
            except ImportError as e:
                print(f"Error: {e}", file=sys.stderr)
                any_error = True
            except ValueError:
                target = entry_target(entry)
                print(f"Error: Identifier not found: {target}", file=sys.stderr)
                print(f"  Run 'ai-guard remove {target}' to remove this entry.", file=sys.stderr)
                any_error = True
    else:
        for target in args.targets:
            for path, identifier in expand_glob_target(root, target):
                try:
                    entries = guard.update(path, identifier)
                    for entry in entries:
                        if entry.identifier:
                            qprint(f"Updated {entry.path}:{entry.identifier} ({entry.hash})")
                        else:
                            qprint(f"Updated {entry.path} ({entry.hash})")
                        pprint(entry_target(entry))
                        any_success = True
                except FileNotFoundError:
                    print(f"Error: File not found: {path}", file=sys.stderr)
                    any_error = True
                except ImportError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    any_error = True
                except ValueError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    any_error = True

    if any_success:
        guard.save()

    return 1 if any_error and not any_success else 0


def cmd_remove(args: argparse.Namespace) -> int:
    """Remove protection for a file or identifier."""
    root = find_project_root()
    guard = GuardFile(root)
    if _check_conflicts(guard):
        return 1

    all_removed = []
    for target in args.targets:
        for path, identifier in expand_glob_target(root, target):
            removed = guard.remove(path, identifier)
            all_removed.extend(removed)

    if all_removed:
        guard.save()
        qprint(f"Removed {len(all_removed)} protection(s)")
        for entry in all_removed:
            pprint(entry_target(entry))
        return 0
    else:
        print("No matching protections found", file=sys.stderr)  # stderr, not qprint
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """List all protected entries."""
    root = find_project_root()
    guard = GuardFile(root)
    if _check_conflicts(guard):
        return 1

    entries = guard.list_entries()
    if not entries:
        qprint("No protected entries")
        return 0

    for entry in entries:
        if _porcelain:
            pprint(entry_target(entry))
        elif entry.identifier:
            qprint(f"{entry.path}:{entry.identifier} ({entry.hash})")
        else:
            qprint(f"{entry.path} ({entry.hash})")

    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify all protected entries."""
    root = find_project_root()
    guard = GuardFile(root)
    if _check_conflicts(guard):
        return 1

    try:
        failures = guard.verify()
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not failures:
        qprint("All protected code verified successfully")
        return 0

    if _porcelain:
        for entry, reason in failures:
            pprint(entry_target(entry))
    else:
        print("AI-Guard violations found:", file=sys.stderr)
        for entry, reason in failures:
            if entry.identifier:
                print(f"  {entry.path}:{entry.identifier} - {reason}", file=sys.stderr)
            else:
                print(f"  {entry.path} - {reason}", file=sys.stderr)

    return 1


def cmd_resolve(args: argparse.Namespace) -> int:
    """Resolve .ai-guard after a merge."""
    root = find_project_root()
    guard = GuardFile(root)

    try:
        resolved, conflicted_files = guard.resolve()
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if conflicted_files:
        print("Error: Guarded source files still have merge conflict markers:", file=sys.stderr)
        for path in conflicted_files:
            print(f"  {path}", file=sys.stderr)
        print("\nResolve these conflicts first, then run 'ai-guard resolve' again.", file=sys.stderr)
        return 1

    guard.save()

    for entry in resolved:
        if entry.identifier:
            qprint(f"Resolved {entry.path}:{entry.identifier} ({entry.hash})")
        else:
            qprint(f"Resolved {entry.path} ({entry.hash})")
        pprint(entry_target(entry))

    qprint(f"Resolved {len(resolved)} entries")
    return 0


_BEGIN_MARKER = "# --- ai-guard {name} ---"
_END_MARKER = "# --- end ai-guard ---"

_PRE_COMMIT_SECTION = """\
# --- ai-guard pre-commit ---
ai-guard verify
if [ $? -ne 0 ]; then
    echo ""
    echo "Commit blocked: Protected code was modified."
    echo "If this change is intentional, run 'ai-guard update <path>' first."
    exit 1
fi
# --- end ai-guard ---"""

_POST_MERGE_SECTION = """\
# --- ai-guard post-merge ---
ai-guard resolve
if [ $? -ne 0 ]; then
    echo ""
    echo "ai-guard resolve failed. Run 'ai-guard resolve' manually"
    echo "after resolving any remaining source conflicts."
fi
# --- end ai-guard ---"""

_MERGE_DRIVER_SCRIPT = """\
#!/bin/sh
# ai-guard merge driver — union merge for .ai-guard files
python3 -c "
from ai_guard.merge_driver import run_merge_driver
import sys
sys.exit(run_merge_driver(sys.argv[1], sys.argv[2], sys.argv[3]))
" "$1" "$2" "$3"
"""

# Old hook pattern (from install-hook, no delimiters)
_OLD_HOOK_START = "# ai-guard pre-commit hook"
_OLD_HOOK_END_PATTERN = "fi\n"


def _find_ai_guard_section(content: str, section_name: str) -> tuple[Optional[int], Optional[int]]:
    """Find the start and end of a delimited ai-guard section in hook content.

    Returns (start, end) character offsets, or (None, None) if not found.
    """
    begin = _BEGIN_MARKER.format(name=section_name)
    start = content.find(begin)
    if start == -1:
        return None, None
    end = content.find(_END_MARKER, start)
    if end == -1:
        return None, None
    end += len(_END_MARKER)
    # Include trailing newline if present
    if end < len(content) and content[end] == "\n":
        end += 1
    return start, end


def _find_old_hook_section(content: str) -> tuple[Optional[int], Optional[int]]:
    """Find the old-style (pre-delimiter) ai-guard section.

    The old install-hook wrote a section starting with '# ai-guard pre-commit hook'
    through the closing 'fi' of the verify check.
    """
    start = content.find(_OLD_HOOK_START)
    if start == -1:
        return None, None
    # Find the 'fi' that closes the if block after ai-guard verify
    fi_pos = content.find("\nfi\n", start)
    if fi_pos == -1:
        # Might be at end of file without trailing newline
        fi_pos = content.find("\nfi", start)
        if fi_pos == -1:
            return None, None
        end = fi_pos + len("\nfi")
    else:
        end = fi_pos + len("\nfi\n")
    return start, end


def _prompt_user(prompt: str) -> bool:
    """Prompt user for y/n confirmation."""
    try:
        response = input(f"{prompt} [y/n] ").strip().lower()
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _install_hook_section(hook_path: Path, section_name: str, section_content: str) -> bool:
    """Install or update an ai-guard section in a hook file.

    Returns True if the section was installed/updated, False if skipped.
    """
    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8")

        # Check for new-style delimited section
        start, end = _find_ai_guard_section(existing, section_name)
        if start is not None:
            current_section = existing[start:end].rstrip("\n")
            if current_section == section_content:
                print(f"\n  {section_name} hook — already installed, up to date")
                return False
            # Show diff and prompt for replacement
            print(f"\n  {section_name} hook")
            print(f"  File: {hook_path}")
            print(f"  Note: Existing ai-guard section found, will be replaced")
            print(f"\n  --- current ai-guard section ---")
            for line in current_section.splitlines():
                print(f"  {line}")
            print(f"\n  --- new ai-guard section ---")
            for line in section_content.splitlines():
                print(f"  {line}")
            print()
            if not _prompt_user("  Replace?"):
                return False
            new_content = existing[:start] + section_content + "\n" + existing[end:]
            hook_path.write_text(new_content, encoding="utf-8")
            hook_path.chmod(0o755)
            return True

        # Check for old-style section (pre-commit only)
        if section_name == "pre-commit":
            old_start, old_end = _find_old_hook_section(existing)
            if old_start is not None:
                current_section = existing[old_start:old_end].rstrip("\n")
                print(f"\n  {section_name} hook")
                print(f"  File: {hook_path}")
                print(f"  Note: Old-style ai-guard section found, will be replaced with delimited version")
                print(f"\n  --- current ai-guard section ---")
                for line in current_section.splitlines():
                    print(f"  {line}")
                print(f"\n  --- new ai-guard section ---")
                for line in section_content.splitlines():
                    print(f"  {line}")
                print()
                if not _prompt_user("  Replace?"):
                    return False
                new_content = existing[:old_start] + section_content + "\n" + existing[old_end:]
                hook_path.write_text(new_content, encoding="utf-8")
                hook_path.chmod(0o755)
                return True

        # No ai-guard section — append
        print(f"\n  {section_name} hook")
        print(f"  File: {hook_path}")
        print(f"  Note: Existing hook found, ai-guard section will be appended")
        print(f"\n  --- content to append ---")
        for line in section_content.splitlines():
            print(f"  {line}")
        print()
        if not _prompt_user("  Install?"):
            return False
        new_content = existing.rstrip() + "\n\n" + section_content + "\n"
        hook_path.write_text(new_content, encoding="utf-8")
        hook_path.chmod(0o755)
        return True
    else:
        # New hook file
        print(f"\n  {section_name} hook")
        print(f"  File: {hook_path}")
        print(f"\n  --- content ---")
        for line in section_content.splitlines():
            print(f"  {line}")
        print()
        if not _prompt_user("  Install?"):
            return False
        full_content = "#!/bin/sh\n" + section_content + "\n"
        hook_path.write_text(full_content, encoding="utf-8")
        hook_path.chmod(0o755)
        return True


def cmd_install_git_hooks(args: argparse.Namespace) -> int:
    """Interactively install git hooks and merge configuration."""
    root = find_project_root()
    hooks_dir = root / ".git" / "hooks"

    if not hooks_dir.exists():
        print("Error: .git/hooks directory not found", file=sys.stderr)
        return 1

    print("ai-guard git hooks installer")
    print("Each item is shown with its content. You are prompted before installation.")

    # 1. Pre-commit hook
    print("\n" + "=" * 60)
    print("1. Pre-commit hook")
    print("   Runs 'ai-guard verify' before each commit. Blocks the")
    print("   commit if protected code was modified without updating hashes.")
    _install_hook_section(hooks_dir / "pre-commit", "pre-commit", _PRE_COMMIT_SECTION)

    # 2. Post-merge hook
    print("\n" + "=" * 60)
    print("2. Post-merge hook")
    print("   Runs 'ai-guard resolve' after a merge completes. Recomputes")
    print("   hashes for all protected entries to match the merged source tree.")
    _install_hook_section(hooks_dir / "post-merge", "post-merge", _POST_MERGE_SECTION)

    # 3. Merge driver
    print("\n" + "=" * 60)
    print("3. Merge driver")
    print("   Configures a custom git merge driver that prevents merge")
    print("   conflicts in .ai-guard. Instead of three-way merging, git")
    print("   keeps all entries from both sides and lets the post-merge")
    print("   hook recompute the correct hashes.")
    _install_merge_driver(root, hooks_dir)

    print()
    return 0


def _install_merge_driver(root: Path, hooks_dir: Path) -> None:
    """Install the merge driver script and configuration."""
    import subprocess

    driver_path = hooks_dir / "ai-guard-merge-driver"
    gitattributes_path = root / ".gitattributes"

    # Check current state
    driver_exists = driver_path.exists()
    driver_current = False
    if driver_exists:
        existing_driver = driver_path.read_text(encoding="utf-8")
        driver_current = existing_driver == _MERGE_DRIVER_SCRIPT

    # Check git config
    config_set = False
    try:
        result = subprocess.run(
            ["git", "config", "--local", "merge.ai-guard.driver"],
            capture_output=True, text=True, cwd=root,
        )
        config_set = result.returncode == 0
    except FileNotFoundError:
        pass

    # Check .gitattributes
    attr_set = False
    if gitattributes_path.exists():
        attr_content = gitattributes_path.read_text(encoding="utf-8")
        attr_set = ".ai-guard merge=ai-guard" in attr_content

    if driver_current and config_set and attr_set:
        print("\n  Merge driver — already installed, up to date")
        return

    # Show what will be changed
    changes = []
    if not driver_current:
        changes.append(f"  Will install: {driver_path}")
        print(f"\n  --- driver script ---")
        for line in _MERGE_DRIVER_SCRIPT.splitlines():
            print(f"  {line}")
    if not config_set:
        changes.append("  Will add to .git/config:")
        changes.append('    [merge "ai-guard"]')
        changes.append(f"        driver = {driver_path} %O %A %B")
        changes.append('        name = ai-guard merge driver')
    if not attr_set:
        changes.append(f"  Will add to .gitattributes:")
        changes.append("    .ai-guard merge=ai-guard")

    if changes:
        print()
        for line in changes:
            print(line)
        print()

    if not _prompt_user("  Install?"):
        return

    # Install driver script
    if not driver_current:
        driver_path.write_text(_MERGE_DRIVER_SCRIPT, encoding="utf-8")
        driver_path.chmod(0o755)

    # Configure git
    if not config_set:
        subprocess.run(
            ["git", "config", "--local", "merge.ai-guard.driver",
             f"{driver_path} %O %A %B"],
            cwd=root, check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "merge.ai-guard.name",
             "ai-guard merge driver"],
            cwd=root, check=True,
        )

    # Update .gitattributes
    if not attr_set:
        if gitattributes_path.exists():
            content = gitattributes_path.read_text(encoding="utf-8")
            content = content.rstrip() + "\n.ai-guard merge=ai-guard\n"
        else:
            content = ".ai-guard merge=ai-guard\n"
        gitattributes_path.write_text(content, encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="ai-guard",
        description="Protect code from incidental modifications by an AI",
        epilog="Run 'ai-guard <command> --help' for help on a specific command.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__import__('ai_guard').__version__}",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress all non-error output",
    )
    parser.add_argument(
        "--porcelain",
        action="store_true",
        help="Produce machine-readable output (one entry per line, no decoration)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # add command
    add_parser = subparsers.add_parser(
        "add", help="Add protection for a file or identifier"
    )
    add_parser.add_argument(
        "targets",
        nargs="+",
        metavar="target",
        help='File or path:identifier to protect. For class members: Python uses Class.method, C/C++ uses Struct::field. Supports globs (quote to prevent shell expansion)',
    )
    add_parser.set_defaults(func=cmd_add)

    # update command
    update_parser = subparsers.add_parser(
        "update", help="Update the hash for a protected entry"
    )
    update_parser.add_argument(
        "--all",
        action="store_true",
        help="Update all existing protected entries",
    )
    update_parser.add_argument(
        "targets",
        nargs="*",
        metavar="target",
        help='File or path:identifier to update. For class members: Python uses Class.method, C/C++ uses Struct::field. Supports globs',
    )
    update_parser.set_defaults(func=cmd_update)

    # remove command
    remove_parser = subparsers.add_parser(
        "remove", help="Remove protection for a file or identifier"
    )
    remove_parser.add_argument(
        "targets",
        nargs="+",
        metavar="target",
        help="File path or path:identifier to unprotect. For class members: Python uses Class.method, C/C++ uses Struct::field",
    )
    remove_parser.set_defaults(func=cmd_remove)

    # list command
    list_parser = subparsers.add_parser("list", help="List all protected entries")
    list_parser.set_defaults(func=cmd_list)

    # verify command
    verify_parser = subparsers.add_parser("verify", help="Verify all protected entries")
    verify_parser.set_defaults(func=cmd_verify)

    # resolve command
    resolve_parser = subparsers.add_parser(
        "resolve",
        help="Resolve .ai-guard after a merge",
        description=(
            "Resolve .ai-guard after a merge. Recomputes all hashes from the current\n"
            "source tree. Entries whose files or identifiers no longer exist are removed.\n\n"
            "Because the user performed the merge and resolved any source conflicts,\n"
            "running resolve treats the merged source as approved. Hashes are recomputed\n"
            "to match the merged result without further confirmation.\n\n"
            "Source files with merge conflict markers will block resolution — resolve\n"
            "those conflicts first."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    resolve_parser.set_defaults(func=cmd_resolve)

    # install-git-hooks command
    install_parser = subparsers.add_parser(
        "install-git-hooks",
        help="Interactively install git hooks and merge configuration",
        description=(
            "Interactively install git hooks and merge configuration for ai-guard.\n"
            "Each item is shown with its content and you are prompted before installation.\n\n"
            "Available items:\n\n"
            "  pre-commit      Runs 'ai-guard verify' before each commit. Blocks the\n"
            "                  commit if protected code was modified without updating\n"
            "                  hashes.\n\n"
            "  post-merge      Runs 'ai-guard resolve' after a merge completes.\n"
            "                  Recomputes hashes for all protected entries to match\n"
            "                  the merged source tree.\n\n"
            "  merge-driver    Configures a custom git merge driver that prevents\n"
            "                  merge conflicts in .ai-guard. Instead of three-way\n"
            "                  merging the file, git keeps all entries from both\n"
            "                  sides and lets the post-merge hook recompute the\n"
            "                  correct hashes. Adds an entry to .gitattributes\n"
            "                  (tracked) and .git/config (local)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    install_parser.set_defaults(func=cmd_install_git_hooks)

    args = parser.parse_args(argv)
    global _quiet, _porcelain
    _porcelain = args.porcelain
    _quiet = args.quiet or _porcelain  # porcelain implies quiet
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
