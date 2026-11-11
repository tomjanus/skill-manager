from __future__ import annotations

import contextlib
import io
import re
import unittest
from unittest import mock

from skill_manager.ui import ConsoleUI

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class ConsoleUITests(unittest.TestCase):
    def test_info_warn_error_emit_no_ansi_without_tty(self) -> None:
        ui = ConsoleUI()
        for method, args in (
            ("info", ("hello",)),
            ("warn", ("warning",)),
            ("error", ("error",)),
        ):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                getattr(ui, method)(*args)
            text = out.getvalue() if method == "info" else err.getvalue()
            self.assertNotIn("\x1b", text)
            self.assertNotRegex(text, _ANSI)

    def test_choose_one_returns_none_when_selection_is_cancelled(self) -> None:
        ui = ConsoleUI()
        with mock.patch("skill_manager.ui.questionary.select") as select:
            select.return_value.ask.return_value = None
            result = ui.choose_one(
                "Choose:", ["first", "second"], lambda _index, item: item, default=1
            )
        self.assertIsNone(result)
