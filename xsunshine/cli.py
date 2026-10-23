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
    total = Result()
    mode = "APPLY" if args.apply else "PREVIEW"
    try:
        with ExitStack() as resources:
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
                    print(f"{event.action.upper()} {event.kind} {name}{detail}")

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
            print(f"XSunshine {__version__} | {mode}")
            for tree in trees:
                result = prune(tree, str(tree.root), apply=args.apply, emit=emit)
                for field in fields(total):
                    setattr(
                        total, field.name, getattr(total, field.name) + getattr(result, field.name)
                    )
            record({"action": "summary", "mode": mode, **asdict(total)})
            print(" ".join(f"{key}={value}" for key, value in asdict(total).items()))
        return 1 if total.errors else 0
    except KeyboardInterrupt:
        print("Interrupted; completed deletions remain applied.", file=sys.stderr)
        return 130
    except (OSError, ValueError) as exc:
        print(f"xsunshine: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
