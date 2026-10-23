"""Terminal-only color formatting with Windows console capability detection."""

import ctypes
import os
from contextlib import AbstractContextManager
from ctypes import wintypes


def _enable_windows_color(stream):
    import msvcrt

    try:
        handle = msvcrt.get_osfhandle(stream.fileno())
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        get_mode = kernel.GetConsoleMode
        get_mode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        get_mode.restype = wintypes.BOOL
        set_mode = kernel.SetConsoleMode
        set_mode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        set_mode.restype = wintypes.BOOL
        original = wintypes.DWORD()
        if not get_mode(handle, ctypes.byref(original)):
            return None
        # ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING.
        if not set_mode(handle, original.value | 0x5):
            return None
        return lambda: set_mode(handle, original.value)
    except OSError, ValueError, AttributeError:
        return None


class Terminal(AbstractContextManager):
    COLORS = {
        "header": "1;36",
        "candidate": "36",
        "deleted": "32",
        "skip": "33",
        "error": "31",
        "visit": "90",
        "keep": "90",
        "total": "1",
    }

    def __init__(self, stream, policy="auto"):
        self.stream = stream
        self.policy = policy
        self.enabled = False
        self.restore = None

    def __enter__(self):
        tty = self.stream.isatty()
        self.enabled = self.policy == "always" or (
            self.policy == "auto"
            and tty
            and not os.environ.get("NO_COLOR")
            and os.environ.get("TERM") != "dumb"
        )
        if self.enabled and tty and os.name == "nt":
            self.restore = _enable_windows_color(self.stream)
            if self.restore is None and self.policy == "auto":
                self.enabled = False
        return self

    def __exit__(self, *args):
        if self.restore:
            self.restore()

    def paint(self, kind, text):
        if self.enabled:
            return f"\x1b[{self.COLORS[kind]}m{text}\x1b[0m"
        return text
