"""Allow running skill-manager with ``python -m skill_manager``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
