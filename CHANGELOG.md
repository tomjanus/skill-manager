# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-11-12

### Added

- Skill bundles: an outermost folder other than the source root, without
  `SKILL.md`, containing at least two distinct skills is a collection;
  installing it installs each member under its own name.
- `list` renders bundles as group headers with member skills indented below;
  a bundle has `partial` status when only some members are installed.
- The interactive `add` picker lets users select either a whole bundle or
  individual member skills. `list --json` stays flat (one row per skill).
- Interactive `add` prompts users to choose a source when a skill name has
  multiple candidates. Non-interactive `add` reports an error; `list` and
  `sync` continue to choose the newest `SKILL.md` by mtime.
- Colourful CLI output: statuses are colour-coded (installed green, outdated
  yellow, broken red, partial cyan) and informational/warning/error messages
  are coloured when the output is a terminal.

### Changed

- Duplicate-name links are considered outdated when they point to a source
  other than the current newest candidate, and `sync` repoints them.

[0.2.0] - 2026-11-11

### Added

- `list` now renders with `rich`, showing full (non-truncated) descriptions
  with wrapping instead of cutting them off.
- `add` offers an interactive `questionary` checkbox picker, so skills can be
  selected without typing full names.
- `--verbose` flag on `list` and `add` to report doubled skills.
- Recursive skill discovery: `SKILL.md` files are found in nested folders
  under the skills directory, with names derived from frontmatter.
- Discovery follows directory symlinks and Windows junctions, with cycle
  detection via realpath, so a cloned skills repo linked inside the skills
  folder is discovered.
- Doubled skills (same name at multiple paths) are resolved by the newest
  `SKILL.md` mtime; the repetition and chosen source are reported under
  `--verbose`.
- New runtime dependencies: `rich` and `questionary`.

### Changed

- The `add` interactive picker now uses `questionary` instead of typed
  numbers; descriptions are no longer truncated in `list` output.

[0.1.0] - 2026-10-21

First public release.

### Added

- `init`, `list`, `add`, `remove` and `sync` commands for managing
  opencode Agent Skills per project.
- Skills are kept in a private source directory and installed into a project
  as a symlink (default) or a copy.
- `.skill-manager.json` manifest recording the selection and the source
  hash of every installed skill, so `sync` can reproduce a project
  elsewhere.
- Windows directory-junction fallback when symbolic links cannot be
  created. Junctions are detected as links, reported as `broken` when their
  source disappears, and are never deleted recursively.
- Configuration file `~/.config/skill-manager/.env` with `SKILLS_DIR` and
  `SKILLS_TARGET_DIR`, overridable per invocation.
- Published to PyPI as `simple-skill-manager`; the `skill-manager` command
  is installed as an alias.
- Continuous integration on Python 3.10 – 3.14, macOS and Windows, plus
  lint, type-check and distribution-build jobs.

[Unreleased]: https://github.com/tomjanus/skill-manager/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/tomjanus/skill-manager/releases/tag/v0.3.0
[0.2.0]: https://github.com/tomjanus/skill-manager/releases/tag/v0.2.0
[0.1.0]: https://github.com/tomjanus/skill-manager/releases/tag/v0.1.0
