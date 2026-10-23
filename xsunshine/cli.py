"""Compact terminal interface. Preview is the default; --apply enables deletion."""

import argparse
import ctypes
import json
import os
import sys
from contextlib import ExitStack
from ctypes import wintypes
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path

from xsunshine import __version__
from xsunshine.core import Event, Result, prune
from xsunshine.filesystem import DirectoryTree
from xsunshine.registry import RegistryTree, normalize_registry_path
from xsunshine.terminal import Terminal


def fixed_drives() -> list[str]:
    if os.name != "nt":
        raise OSError("System-wide Windows cleanup requires Windows")
    get_type = ctypes.WinDLL("kernel32", use_last_error=True).GetDriveTypeW
    get_type.argtypes = [wintypes.LPCWSTR]
    get_type.restype = wintypes.UINT
    roots = [drive for drive in os.listdrives() if get_type(drive) == 3]
    letters = {root.casefold() for root in roots}
    for volume in os.listvolumes():
        if get_type(volume) == 3 and not any(
            mount.casefold() in letters for mount in os.listmounts(volume)
        ):
            roots.append(volume)
    return roots


def outermost(paths: list[str], separator: str) -> list[str]:
    """Deduplicate nested scopes, preserving their broadest boundary."""
    result = []
    for path in sorted(set(paths), key=lambda item: (len(item), item.casefold())):
        folded = path.casefold()
        if not any(
            folded == parent.casefold()
            or folded.startswith(parent.rstrip(separator).casefold() + separator)
            for parent in result
        ):
            result.append(path)
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="xsunshine",
        allow_abbrev=False,
        description="Recursively remove empty directories and Windows registry keys.",
        epilog="Scopes are retained. Preview is the default; --apply enables deletion.",
    )
    command.add_argument("--version", action="version", version=f"XSunshine {__version__}")
    command.add_argument(
        "--path",
        action="append",
        default=[],
        metavar="DIRECTORY",
        help="directory scope; repeat for multiple locations",
    )
    command.add_argument(
        "--registry",
        action="append",
        default=[],
        metavar="KEY",
        help=r"registry scope, e.g. HKCU\Software; repeat as needed",
    )
    command.add_argument(
        "--all", action="store_true", help="all local fixed volumes and loaded HKLM/HKU hives"
    )
    command.add_argument(
        "--registry-view",
        choices=("32", "64", "both"),
        default="both",
        help="Windows registry view (default: both)",
    )
    command.add_argument("--apply", action="store_true", help="perform the deletions")
    command.add_argument("--trace", metavar="FILE", help="write diagnostic JSONL to a new file")
    command.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="terminal colors (default: auto; honors NO_COLOR)",
    )
    command.add_argument(
        "--verbose", action="store_true", help="also print visits and retained items"
    )
    return command


def main(argv: list[str] | None = None) -> int:
    command = parser()
    args = command.parse_args(argv)
    if not (args.all or args.path or args.registry):
        command.error("select --path, --registry, or --all")
    if args.all and (args.path or args.registry):
        command.error("use --all by itself or supply explicit scopes")
    if any(not path or "\x00" in path for path in args.path):
        command.error("directory paths must be nonempty and contain no NUL characters")
    try:
        directories = outermost([os.path.abspath(path) for path in args.path], os.sep)
        registries = outermost([normalize_registry_path(key) for key in args.registry], "\\")
    except ValueError as exc:
        command.error(str(exc))
    totals = {}
    mode = "APPLY" if args.apply else "PREVIEW"
    try:
        with ExitStack() as resources:
            terminal = resources.enter_context(Terminal(sys.stdout, args.color))
            log = (
                resources.enter_context(Path(args.trace).open("x", encoding="utf-8"))
                if args.trace
                else None
            )

            def record(data):
                if log:
                    log.write(
                        json.dumps(
                            {"time": datetime.now(timezone.utc).isoformat(), **data},
                            ensure_ascii=True,
                        )
                        + "\n"
                    )
                    log.flush()

            def emit(event: Event):
                record(asdict(event))
                if args.verbose or event.action not in ("visit", "keep"):
                    # JSON quoting prevents control characters in names from
                    # becoming terminal commands or misleading extra lines.
                    name = json.dumps(event.path, ensure_ascii=True)
                    detail = " " + json.dumps(event.detail) if event.detail else ""
                    label = terminal.paint(event.action, event.action.upper())
                    print(f"{label} {event.kind} {name}{detail}", flush=True)

            if args.all:
                directories = fixed_drives()
                registries = ["HKLM", "HKU"]
            views = ("32", "64") if args.registry_view == "both" else (args.registry_view,)
            trees = [DirectoryTree(path) for path in directories]
            trees.extend(RegistryTree(key, view) for key in registries for view in views)
            record(
                {
                    "action": "start",
                    "version": __version__,
                    "mode": mode,
                    "directories": directories,
                    "registries": registries,
                    "views": views,
                }
            )
            print(terminal.paint("header", f"XSunshine {__version__} | {mode}"), flush=True)
            status, exit_code = "completed", 0
            try:
                for tree in trees:
                    progress = totals.setdefault(tree.kind, Result())
                    prune(tree, str(tree.root), apply=args.apply, emit=emit, result=progress)
            except KeyboardInterrupt:
                status, exit_code = "interrupted", 130
                print("Interrupted; completed deletions remain applied.", file=sys.stderr)
            except (OSError, ValueError) as exc:
                status, exit_code = "failed", 1
                print(f"xsunshine: {exc}", file=sys.stderr)

            total = Result(
                **{
                    field.name: sum(getattr(row, field.name) for row in totals.values())
                    for field in fields(Result)
                }
            )
            if total.errors and status == "completed":
                status, exit_code = "incomplete", 1
            labels = {
                "directory": "Directories",
                "registry32": "Registry (32-bit)",
                "registry64": "Registry (64-bit)",
            }

            def counts(result):
                return " ".join(f"{key}={value}" for key, value in asdict(result).items())

            for kind, row in totals.items():
                print(f"{labels[kind]}: {counts(row)}")
            suffix = f", {status}" if status != "completed" else ""
            print(terminal.paint("total", f"TOTAL ({mode}{suffix}): {counts(total)}"), flush=True)
            record(
                {
                    "action": "summary",
                    "mode": mode,
                    "status": status,
                    "by_kind": {kind: asdict(row) for kind, row in totals.items()},
                    **asdict(total),
                }
            )
        return exit_code
    except KeyboardInterrupt:
        print("Interrupted; completed deletions remain applied.", file=sys.stderr)
        return 130
    except (OSError, ValueError) as exc:
        print(f"xsunshine: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
