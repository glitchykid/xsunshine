"""Iterative post-order pruning shared by filesystem and registry backends."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Snapshot:
    children: tuple[str, ...]
    has_content: bool
    identity: object = None


@dataclass(frozen=True)
class Event:
    action: str
    kind: str
    path: str
    detail: str = ""


@dataclass
class Result:
    visited: int = 0
    candidates: int = 0
    deleted: int = 0
    skipped: int = 0
    errors: int = 0


class Skipped(Exception):
    """A link or changed object must remain untouched."""


class ReportingError(RuntimeError):
    """Reporting is unavailable; stop traversal rather than hiding lost output."""


class Tree(Protocol):
    kind: str

    def inspect(self, node: str) -> Snapshot: ...

    def remove_empty(self, node: str, identity: object) -> bool: ...


def prune(
    tree: Tree,
    root: str,
    *,
    apply: bool = False,
    emit: Callable[[Event], None] = lambda event: None,
    result: Result | None = None,
) -> Result:
    """Prune descendants; the explicit scope root is always retained.

    Preview models removal of children so parents are reported in the same pass.
    Apply rechecks every object and delegates only non-recursive removal.
    A supplied result retains progress if traversal is interrupted.
    """
    if result is None:
        result = Result()

    def report(event):
        try:
            emit(event)
        except OSError as exc:
            # Keep output failures out of the per-object access-error handler.
            raise ReportingError(f"Unable to report cleanup progress: {exc}") from exc

    removed: set[str] = set()
    stack: list[tuple[str, Snapshot | None]] = [(root, None)]
    while stack:
        node, before = stack.pop()
        try:
            current = tree.inspect(node)
            if before is None:
                result.visited += 1
                report(Event("visit", tree.kind, node))
                stack.append((node, current))
                stack.extend((child, None) for child in reversed(current.children))
                continue
            if current.identity != before.identity:
                raise Skipped("Object changed during traversal")
            if node == root:
                report(Event("keep", tree.kind, node, "Scope root"))
                continue
            if current.has_content or any(child not in removed for child in current.children):
                report(Event("keep", tree.kind, node, "Contains content or retained children"))
                continue
            result.candidates += 1
            if apply:
                if not tree.remove_empty(node, before.identity):
                    raise Skipped("No longer empty or changed before deletion")
                result.deleted += 1
                report(Event("deleted", tree.kind, node))
            else:
                report(Event("candidate", tree.kind, node))
            removed.add(node)
        except Skipped as exc:
            result.skipped += 1
            report(Event("skip", tree.kind, node, str(exc)))
        except OSError as exc:
            result.errors += 1
            report(Event("error", tree.kind, node, str(exc)))
    return result
