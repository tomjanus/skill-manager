# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-21

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

[Unreleased]: https://github.com/tomjanus/skill-manager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tomjanus/skill-manager/releases/tag/v0.1.0
