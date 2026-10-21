"""User interaction abstractions.

The console implementation prints to stdout/stderr; tests substitute a
fake that records calls. Keeping I/O behind this small interface makes the
operation logic testable without a terminal.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import Protocol, TypeVar

T = TypeVar("T")


class UI(Protocol):
    """Minimal interface the operations need from a user interface."""

    def info(self, message: str = "") -> None: ...

    def warn(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def confirm(self, question: str, default: bool = False) -> bool: ...

    def choose_many(
        self,
        items: Sequence[T],
        render: Callable[[int, T], str],
    ) -> list[T]: ...


class ConsoleUI:
    """Interactive UI backed by stdin/stdout/stderr."""

    def info(self, message: str = "") -> None:
        print(message)

    def warn(self, message: str) -> None:
        print(f"warning: {message}", file=sys.stderr)

    def error(self, message: str) -> None:
        print(f"error: {message}", file=sys.stderr)

    def confirm(self, question: str, default: bool = False) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        try:
            answer = input(f"{question} {suffix} ").strip().lower()
        except EOFError:
            return default
        if not answer:
            return default
        return answer in ("y", "yes")

    def choose_many(
        self,
        items: Sequence[T],
        render: Callable[[int, T], str],
    ) -> list[T]:
        if not items:
            return []
        for index, item in enumerate(items, start=1):
            print(f"  {index:>3}. {render(index, item)}")
        try:
            answer = input(
                "Select skills (comma-separated numbers, 'all', empty to cancel): "
            ).strip()
        except EOFError:
            return []
        if not answer:
            return []
        if answer.lower() == "all":
            return list(items)
        selected: list[T] = []
        for part in answer.split(","):
            part = part.strip()
            if not part.isdigit():
                continue
            number = int(part)
            if 1 <= number <= len(items):
                selected.append(items[number - 1])
        return selected


class FakeUI:
    """Non-interactive UI for tests."""

    def __init__(
        self,
        confirm_answer: bool = True,
        chosen: Sequence[int] | None = None,
    ) -> None:
        self.confirm_answer = confirm_answer
        self.chosen = list(chosen) if chosen is not None else []
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.confirmations: list[str] = []

    def info(self, message: str = "") -> None:
        self.infos.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def confirm(self, question: str, default: bool = False) -> bool:
        self.confirmations.append(question)
        return self.confirm_answer

    def choose_many(
        self,
        items: Sequence[T],
        render: Callable[[int, T], str],
    ) -> list[T]:
        return [items[index] for index in self.chosen if 0 <= index < len(items)]
