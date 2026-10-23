import io
import unittest
from unittest.mock import patch

from xsunshine.terminal import Terminal


class TerminalTests(unittest.TestCase):
    def test_terminal_auto_color_and_console_restoration(self):
        output = io.StringIO()
        output.isatty = lambda: True
        restored = []
        with (
            patch.dict("os.environ", {"TERM": "xterm", "NO_COLOR": ""}),
            patch(
                "xsunshine.terminal._enable_windows_color",
                return_value=lambda: restored.append(True),
            ),
        ):
            with Terminal(output, "auto") as terminal:
                self.assertEqual(terminal.paint("deleted", "DELETED"), "\x1b[32mDELETED\x1b[0m")
        import os

        if os.name == "nt":
            self.assertEqual(restored, [True])

    def test_no_color_and_dumb_term_disable_automatic_colors(self):
        output = io.StringIO()
        output.isatty = lambda: True
        for environment in [{"NO_COLOR": "1"}, {"TERM": "dumb"}]:
            with self.subTest(environment=environment), patch.dict("os.environ", environment):
                with Terminal(output, "auto") as terminal:
                    self.assertEqual(terminal.paint("error", "ERROR"), "ERROR")

    def test_always_overrides_environment_and_never_disables_colors(self):
        with patch.dict("os.environ", {"NO_COLOR": "1", "TERM": "dumb"}):
            with Terminal(io.StringIO(), "always") as terminal:
                self.assertEqual(terminal.paint("error", "ERROR"), "\x1b[31mERROR\x1b[0m")
            with Terminal(io.StringIO(), "never") as terminal:
                self.assertEqual(terminal.paint("error", "ERROR"), "ERROR")

    def test_unavailable_windows_console_falls_back_to_plain_text(self):
        output = io.StringIO()
        output.isatty = lambda: True
        with (
            patch.dict("os.environ", {"TERM": "xterm", "NO_COLOR": ""}),
            patch("xsunshine.terminal.os.name", "nt"),
            patch("xsunshine.terminal._enable_windows_color", return_value=None),
        ):
            with Terminal(output, "auto") as terminal:
                self.assertEqual(terminal.paint("skip", "SKIP"), "SKIP")
