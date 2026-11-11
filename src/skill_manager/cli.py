"""Command line interface for skill-manager."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import config
from .manifest import ManifestError
from .operations import (
    STATUS_BROKEN,
    STATUS_EXTERNAL,
    STATUS_INSTALLED,
    STATUS_MISSING,
    STATUS_MISSING_SOURCE,
    STATUS_NOT_INSTALLED,
    STATUS_OUTDATED,
    STATUS_PARTIAL,
    Manager,
    SkillTreeNode,
    SkillView,
)
from .platform import LinkError
from .project import find_project_root
from .ui import ConsoleUI

DESCRIPTION = (
    "Manager of opencode Agent Skills: keeps them in a private folder and "
    "links or copies the ones a project needs."
)

PROG = "simple-skill-manager"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, description=DESCRIPTION)
    parser.add_argument(
        "--skills-dir",
        help="Source skills directory (overrides SKILLS_DIR in the env file).",
    )
    parser.add_argument(
        "--target-dir",
        help="Project target directory (overrides SKILLS_TARGET_DIR).",
    )
    parser.add_argument(
        "--root",
        help="Project root (defaults to the enclosing git worktree).",
    )
    parser.add_argument(
        "--env-file",
        help="Environment file (defaults to ~/.config/skill-manager/.env).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create the configuration file and source directory.")

    list_parser = sub.add_parser("list", help="List available and installed skills.")
    list_parser.add_argument(
        "--available",
        action="store_true",
        help="Show only skills in the source directory.",
    )
    list_parser.add_argument(
        "--installed",
        action="store_true",
        help="Show only skills installed in the project.",
    )
    list_parser.add_argument("--json", action="store_true", help="Output JSON.")
    list_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Report duplicate skills and the newest source chosen.",
    )

    add_parser = sub.add_parser("add", help="Add skills to the project.")
    add_parser.add_argument(
        "names", nargs="*", help="Skill names (interactive if omitted)."
    )
    add_parser.add_argument(
        "--copy", action="store_true", help="Copy skills instead of linking them."
    )
    add_parser.add_argument(
        "--force", action="store_true", help="Replace existing or unmanaged targets."
    )
    add_parser.add_argument(
        "--yes", action="store_true", help="Do not ask for confirmation."
    )
    add_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Report duplicate skills and the newest source default.",
    )

    remove_parser = sub.add_parser("remove", help="Remove skills from the project.")
    remove_parser.add_argument("names", nargs="+", help="Skill names to remove.")
    remove_parser.add_argument(
        "--yes", action="store_true", help="Do not ask for confirmation."
    )
    remove_parser.add_argument(
        "--force",
        action="store_true",
        help="Remove targets not managed by skill-manager.",
    )

    sync_parser = sub.add_parser(
        "sync", help="Update installed skills from their source."
    )
    sync_parser.add_argument(
        "--yes", action="store_true", help="Do not ask for confirmation."
    )
    sync_parser.add_argument(
        "--force", action="store_true", help="Apply updates without asking."
    )

    return parser


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    env_file = Path(args.env_file) if args.env_file else config.default_env_file()
    project_root = find_project_root(Path.cwd(), Path(args.root) if args.root else None)
    skills_dir = config.resolve_skills_dir(args.skills_dir, env_file)
    target_dir = config.resolve_target_dir(args.target_dir, env_file, project_root)
    return env_file, project_root, skills_dir, target_dir


_STATUS_STYLES = {
    STATUS_INSTALLED: "green",
    STATUS_OUTDATED: "yellow",
    STATUS_BROKEN: "red",
    STATUS_PARTIAL: "cyan",
    STATUS_MISSING: "yellow",
    STATUS_MISSING_SOURCE: "dim",
    STATUS_NOT_INSTALLED: "dim",
    STATUS_EXTERNAL: "dim",
}


def _status_cell(status: str) -> Text:
    return Text(status, style=_STATUS_STYLES.get(status, "default"))


def _mode_cell(view: SkillView) -> Text:
    return Text(view.mode or "—", style="default" if view.mode else "dim")


def _description_cell(view: SkillView) -> str:
    if view.status == STATUS_EXTERNAL:
        return f"{view.description}  (managed by opencode)"
    return view.description


def _table() -> Table:
    table = Table(show_header=True, header_style="bold")
    table.add_column("NAME")
    table.add_column("STATUS")
    table.add_column("MODE")
    table.add_column("DESCRIPTION")

    return table


def _print_table(views: list[SkillView]) -> None:
    console = Console()
    table = _table()
    for view in views:
        name: str | Text = view.name
        if view.status == STATUS_EXTERNAL:
            name = Text(view.name, style="dim")
        table.add_row(
            name,
            _status_cell(view.status),
            _mode_cell(view),
            _description_cell(view),
        )
    console.print(table)


def _print_tree_table(roots: list[SkillTreeNode]) -> None:
    console = Console()
    table = _table()
    for node in roots:
        view = node.view
        if node.children:
            name: str | Text = Text(f"📦 {view.name} (bundle)", style="bold")
        elif view.status == STATUS_EXTERNAL:
            name = Text(view.name, style="dim")
        else:
            name = view.name
        table.add_row(
            name,
            _status_cell(view.status),
            _mode_cell(view),
            _description_cell(view),
        )
        for index, child in enumerate(node.children):
            branch = "└─ " if index == len(node.children) - 1 else "├─ "
            child_name: str | Text = f"  {branch}{child.view.name}"
            if child.view.status == STATUS_EXTERNAL:
                child_name = Text(str(child_name), style="dim")
            table.add_row(
                child_name,
                _status_cell(child.view.status),
                _mode_cell(child.view),
                _description_cell(child.view),
            )
    console.print(table)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ui = ConsoleUI()

    try:
        env_file, project_root, skills_dir, target_dir = _resolve_paths(args)
        manager = Manager(project_root, skills_dir, target_dir, env_file, ui)

        if args.command == "init":
            manager.init()
            return 0

        if args.command == "list":
            views, tree_roots = manager.list_data(verbose=args.verbose)
            if args.available:
                views = [v for v in views if v.source_path is not None]
            if args.installed:
                views = [v for v in views if v.target_path is not None]
            if args.json:
                print(json.dumps([v.to_dict() for v in views], indent=2))
            elif (
                not args.available
                and not args.installed
                and any(node.children for node in tree_roots)
            ):
                _print_tree_table(tree_roots)
            else:
                _print_table(views)
            return 0

        if args.command == "add":
            if not args.names and not sys.stdin.isatty():
                ui.error(
                    "No skill names given (interactive selection needs a terminal)."
                )
                return 1
            ok = manager.add(
                names=args.names,
                mode="copy" if args.copy else "link",
                force=args.force,
                yes=args.yes,
                interactive=sys.stdin.isatty(),
                verbose=args.verbose,
            )
            return 0 if ok else 1

        if args.command == "remove":
            ok = manager.remove(args.names, yes=args.yes, force=args.force)
            return 0 if ok else 1

        if args.command == "sync":
            ok = manager.sync(yes=args.yes, force=args.force)
            return 0 if ok else 1

        parser.error(f"Unknown command: {args.command}")
        return 2
    except ManifestError as exc:
        ui.error(str(exc))
        return 1
    except LinkError as exc:
        ui.error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
