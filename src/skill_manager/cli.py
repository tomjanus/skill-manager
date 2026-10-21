"""Command line interface for skill-manager."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config
from .manifest import ManifestError
from .operations import Manager, SkillView
from .platform import LinkError
from .project import find_project_root
from .ui import ConsoleUI

DESCRIPTION = (
    "Manage opencode Agent Skills: discover skills in a private folder and "
    "link or copy them into a project."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill-manager", description=DESCRIPTION)
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


def _print_table(views: list[SkillView]) -> None:
    name_width = max([len("NAME")] + [len(v.name) for v in views])
    status_width = max([len("STATUS")] + [len(v.status) for v in views])
    mode_width = max([len("MODE")] + [len(v.mode or "—") for v in views])
    header = (
        f"{'NAME':<{name_width}}  {'STATUS':<{status_width}}  "
        f"{'MODE':<{mode_width}}  DESCRIPTION"
    )
    print(header)
    for view in views:
        description = view.description
        if len(description) > 60:
            description = description[:57] + "..."
        managed = "  (managed by opencode)" if view.status == "external" else ""
        print(
            f"{view.name:<{name_width}}  {view.status:<{status_width}}  "
            f"{(view.mode or '—'):<{mode_width}}  {description}{managed}"
        )


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
            views = manager.list_views()
            if args.available:
                views = [v for v in views if v.source_path is not None]
            if args.installed:
                views = [v for v in views if v.target_path is not None]
            if args.json:
                print(json.dumps([v.to_dict() for v in views], indent=2))
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
                interactive=not args.names,
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
