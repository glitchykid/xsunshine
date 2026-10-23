"""Literal, non-recursive removal of empty directories."""

import errno
import os
import stat
from pathlib import Path

from xsunshine.core import Skipped, Snapshot


class DirectoryTree:
    kind = "directory"

    def __init__(self, root: str | Path):
        self.root = Path(os.path.abspath(root))

    def _checked(self, node: str) -> tuple[Path, os.stat_result]:
        path = Path(os.path.abspath(node))
        if path != self.root and self.root not in path.parents:
            raise ValueError("Directory is outside the selected scope")
        # Include ancestors above the scope: an explicitly supplied path can
        # itself traverse a junction. Do not resolve paths and hide those links.
        for ancestor in (*reversed(path.parents), path):
            info = ancestor.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise Skipped("Symbolic link, junction, or other reparse point")
        if not stat.S_ISDIR(info.st_mode):
            raise NotADirectoryError(str(path))
        return path, info

    def inspect(self, node: str) -> Snapshot:
        path, info = self._checked(node)
        children = []
        has_files = False
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    entry_info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    # A disappearing entry must not abandon the whole directory.
                    # Later inspection and non-recursive deletion still recheck it.
                    continue
                if (
                    stat.S_ISDIR(entry_info.st_mode)
                    or stat.S_ISLNK(entry_info.st_mode)
                    or getattr(entry_info, "st_file_attributes", 0) & 0x400
                ):
                    children.append(entry.path)
                else:
                    has_files = True
        return Snapshot(tuple(sorted(children)), has_files, (info.st_dev, info.st_ino))

    def remove_empty(self, node: str, identity: object) -> bool:
        path, info = self._checked(node)
        if path == self.root:
            raise ValueError("The selected scope root cannot be removed")
        if identity != (info.st_dev, info.st_ino):
            return False
        try:
            # rmdir refuses nonempty directories, including hidden/zero-byte files.
            path.rmdir()
            return True
        except OSError as exc:
            if exc.errno in (errno.ENOTEMPTY, errno.EEXIST) or getattr(exc, "winerror", 0) == 145:
                return False
            raise
