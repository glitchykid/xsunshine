"""Run from a checkout without changing the caller's working directory."""

from xsunshine.cli import entrypoint

if __name__ == "__main__":
    raise SystemExit(entrypoint())
