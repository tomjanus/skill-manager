"""Configuration and path resolution for skill-manager.

The source skills directory is resolved with the following precedence:

1. ``--skills-dir`` command line flag
2. ``SKILLS_DIR`` in the environment file (default ``~/.config/skill-manager/.env``)
3. built-in default ``~/skills``

The target directory is resolved with:

1. ``--target-dir`` command line flag
2. ``SKILLS_TARGET_DIR`` in the environment file
3. ``<project root>/.opencode/skills``
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

DEFAULT_SKILLS_DIR = Path("~/skills")
ENV_FILE_NAME = ".env"
PACKAGE_DIR_NAME = "skill-manager"
SKILLS_DIR_KEY = "SKILLS_DIR"
TARGET_DIR_KEY = "SKILLS_TARGET_DIR"


def default_config_dir() -> Path:
    """Return the directory that holds this tool's configuration."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / PACKAGE_DIR_NAME


def default_env_file() -> Path:
    """Return the default environment file path."""
    return default_config_dir() / ENV_FILE_NAME


def expand_path(value: str) -> Path:
    """Expand ``~`` and environment variables in *value* and return a Path."""
    return Path(os.path.expandvars(os.path.expanduser(value)))


def read_env_file(path: Path) -> dict[str, str]:
    """Parse a minimal ``KEY=VALUE`` environment file.

    Blank lines and lines starting with ``#`` are ignored. Surrounding
    single or double quotes are stripped. Missing files yield an empty
    mapping.
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def resolve_skills_dir(
    cli_value: str | None,
    env_file: Path,
    env_values: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the source skills directory using the documented precedence."""
    if cli_value:
        return expand_path(cli_value)
    values = read_env_file(env_file) if env_values is None else env_values
    configured = values.get(SKILLS_DIR_KEY)
    if configured:
        return expand_path(configured)
    return expand_path(str(DEFAULT_SKILLS_DIR))


def resolve_target_dir(
    cli_value: str | None,
    env_file: Path,
    project_root: Path,
    env_values: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the project target directory using the documented precedence."""
    if cli_value:
        return expand_path(cli_value)
    values = read_env_file(env_file) if env_values is None else env_values
    configured = values.get(TARGET_DIR_KEY)
    if configured:
        return expand_path(configured)
    return project_root / ".opencode" / "skills"


def write_default_env_file(env_file: Path, skills_dir: Path) -> bool:
    """Create *env_file* with default settings if it does not already exist.

    Returns ``True`` when the file was created, ``False`` when it already
    existed.
    """
    if env_file.exists():
        return False
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(
        f"# skill-manager configuration\n{SKILLS_DIR_KEY}={skills_dir}\n",
        encoding="utf-8",
    )
    return True
