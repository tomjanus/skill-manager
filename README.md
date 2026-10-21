# skill-manager

Keep your opencode **Agent Skills** in a private folder, then link or copy
the ones a project needs — without hand-managing symlinks.

The problem it solves: opencode discovers skills from
`~/.config/opencode/skills/`, `~/.claude/skills/`, and `~/.agents/skills/`.
Loading every skill you own into every session is noise. But copying or
linking skills into each project by hand is tedious.

`skill-manager` keeps your skills in a folder of your choosing (by default
`~/skills`, which opencode does **not** discover), lets you browse them, and
adds the ones you want to a specific project — as a symlink or a copy.

- **Linux, macOS, and Windows** (Windows uses a directory junction when
  symlinks are unavailable).
- **No runtime dependencies** — Python 3.10+ standard library only.
- **Reproducible** — the project's selection is recorded in a committed
  manifest, so `skill-manager sync` can restore it anywhere.

---

## Install

With [pipx](https://pipx.pypa.io/):

```bash
pipx install /path/to/skill-manager
```

or, with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install /path/to/skill-manager
```

Both install the `skill-manager` command onto your `PATH` in an isolated
environment, so the tool's dependencies never touch your system Python.

From a clone of this repository:

```bash
git clone <this-repo> ~/src/skill-manager
pipx install ~/src/skill-manager
```

Later upgrades:

```bash
pipx upgrade skill-manager
uv tool upgrade skill-manager
```

To run it without installing:

```bash
PYTHONPATH=src python -m skill_manager --help
```

To uninstall:

```bash
pipx uninstall skill-manager
uv tool uninstall skill-manager
```

---

## Getting started

### 1. Initialise the configuration

```bash
skill-manager init
```

This creates:

| Path | Purpose |
| --- | --- |
| `~/.config/skill-manager/.env` | Configuration file (`SKILLS_DIR=~/skills`) |
| `~/skills` | Your private skills folder (created if missing) |

`init` is idempotent — run it again any time; existing files are left alone.

### 2. Put your skills in the source folder

Each skill is a directory containing a `SKILL.md` with YAML frontmatter:

```
~/skills/
├── scientific-python/
│   ├── SKILL.md
│   └── references/
└── tdd/
    └── SKILL.md
```

`~/skills/scientific-python/SKILL.md`:

```markdown
---
name: scientific-python
description: Reliable and reproducible Python scientific computing.
---

# Scientific Python
...
```

`SKILL.md` must be in ALL CAPS. The `name` field must match the directory
name and be lowercase alphanumeric with single hyphens.

### 3. Add skills to a project

```bash
cd ~/projects/my-project
skill-manager add                 # interactive picker
skill-manager add tdd scientific-python
skill-manager add tdd --copy      # copy instead of linking
```

`add` writes into `<project root>/.opencode/skills/<name>/`, which is where
opencode looks for project skills. The project root is the enclosing git
worktree, so the command works from any subdirectory.

### 4. See what you have

```bash
skill-manager list
```

```
NAME                STATUS        MODE    DESCRIPTION
scientific-python   installed     link    Reliable and reproducible Python scientific...
tdd                 outdated      copy    Test-first implementation and regression...
pdf                 external      —       (managed by opencode)
water-distribution  not-installed —       Water-distribution networks, hydraulics...
```

`list --json` emits the same information as JSON for scripting.

---

## Commands

### `skill-manager init`

Creates the configuration file and the source skills directory if they do
not exist. Safe to re-run.

### `skill-manager list`

Merges three sources of truth — your source folder, the project's
`.opencode/skills/` folder, and the project manifest — into one table.

| Status | Meaning |
| --- | --- |
| `installed` | Present and matching the source |
| `outdated` | A copy whose source has changed |
| `broken` | A link whose target has disappeared |
| `missing` | In the manifest, but not in the project folder |
| `missing-source` | In the project, but gone from the source folder |
| `not-installed` | Available in the source folder, not in the project |
| `external` | In the project folder but **not** managed by `skill-manager` (for example opencode's own installer) |

Flags: `--available` (source only), `--installed` (project only), `--json`.

### `skill-manager add [NAME ...]`

Adds skills to the project.

- With no names, opens an interactive picker (numbers, comma-separated,
  or `all`). Requires a terminal.
- **Links by default**, so edits to the source skill are picked up
  immediately. Use `--copy` for a frozen snapshot.
- If the skill is already installed and unchanged, reports `already up to
  date` and does nothing.
- If the source changed, or the link is broken, you are asked before
  updating. `--yes` accepts all updates.
- If the target exists but is **not** managed by `skill-manager`, the
  command refuses to touch it. `--force` replaces it.

Flags: `--copy`, `--force`, `--yes`.

### `skill-manager remove NAME ...`

Removes skills from the project folder and from the manifest. You are asked
for confirmation unless `--yes` is given. Skills not managed by
`skill-manager` are only removed with `--force`.

Flags: `--yes`, `--force`.

### `skill-manager sync`

Reconciles the skills **already installed** in the project with their
source. It never adds new skills.

- A copy whose source changed is updated after confirmation.
- A missing or broken link is re-created.
- A skill whose source disappeared is offered for removal.
- Anything unchanged is reported as `up to date`.

Flags: `--yes`, `--force`.

---

## Configuration

Settings live in `~/.config/skill-manager/.env`:

```bash
# Where your skills live.
SKILLS_DIR=~/skills

# Optional: override the project target folder.
SKILLS_TARGET_DIR=~/projects/my-project/.opencode/skills
```

The file is a minimal `KEY=VALUE` file: `#` comments and blank lines are
ignored, and values may be quoted.

### Precedence

**Source directory** (`SKILLS_DIR`):

1. `--skills-dir <path>` on the command line
2. `SKILLS_DIR` in the environment file
3. `~/skills`

**Target directory** (`SKILLS_TARGET_DIR`):

1. `--target-dir <path>` on the command line
2. `SKILLS_TARGET_DIR` in the environment file
3. `<project root>/.opencode/skills`

**Project root**:

1. `--root <path>` on the command line
2. the enclosing git worktree
3. the current directory

**Environment file**: `--env-file <path>`, default
`~/.config/skill-manager/.env`.

Global flags (`--skills-dir`, `--target-dir`, `--root`, `--env-file`) may be
given before the subcommand:

```bash
skill-manager --skills-dir /opt/skills list
```

---

## The project manifest

Each project records its selection in `.skill-manager.json` at the project
root:

```json
{
  "skills": {
    "scientific-python": {
      "hash": "3f2a…",
      "mode": "link"
    },
    "tdd": {
      "hash": "9b71…",
      "mode": "copy"
    }
  },
  "version": 1
}
```

- `mode` is `link` or `copy`.
- `hash` is the SHA-256 of the source skill at the time it was added or
  last updated. It is how `sync` detects that a source has changed.

This file is intended to be **committed** — it is what makes a project's
skill selection reproducible on another machine:

```bash
git clone <repo> && cd <repo>
skill-manager sync
```

The target folder `.opencode/skills/` is a build artefact; it is usually
git-ignored.

---

## Windows notes

Windows requires either Administrator rights or Developer Mode to create
symbolic links. When `os.symlink` fails, `skill-manager` falls back to a
directory **junction** (`mklink /J`), which needs neither. If even that
fails, use `--copy`.

Windows paths containing backslashes or spaces are handled correctly in the
`.env` file, but remember that `KEY=VALUE` splits on the first `=`, so a
value containing `=` should be quoted.

---

## Development

```bash
git clone <this-repo> && cd skill-manager
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Run the tests (standard library only, no test dependencies):

```bash
PYTHONPATH=src python -m unittest discover -s tests -t .
```

Optional development tools (not required to use the CLI):

```bash
pip install ruff mypy
ruff check src tests
ruff format --check src tests
mypy
```

### Layout

```
src/skill_manager/
├── cli.py          # argument parsing, table output, command dispatch
├── config.py       # env file parsing, path precedence
├── discovery.py    # scanning the source folder, frontmatter, hashing
├── manifest.py     # reading and writing .skill-manager.json
├── operations.py   # init / list / add / remove / sync
├── platform.py     # symlink, junction, copy, remove
├── project.py      # project root discovery, scanning the target folder
└── ui.py           # console interaction (and a fake for tests)
```

---

## License

MIT
