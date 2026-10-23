# XSunshine

XSunshine is a Windows terminal application that recursively removes empty filesystem directories and empty registry keys. It visits children before parents, so a parent made empty by cleanup can be removed in the same run.

## Requirements

- Windows and the latest stable [Python](https://www.python.org/downloads/windows/) (developed and tested with **3.15.1**, 64-bit).
- The optional launcher uses the latest stable [PowerShell](https://github.com/PowerShell/PowerShell/releases/latest) (tested with **7.6.8**).
- No third-party runtime dependencies. Python handles traversal and Windows APIs directly; PowerShell only launches the application.

## Getting started

```powershell
git clone https://github.com/glitchykid/xsunshine.git
cd xsunshine
python -m xsunshine --help
```

Preview a chosen directory or registry branch:

```powershell
python -m xsunshine --path 'C:\Example'
python -m xsunshine --registry 'HKCU\Software' --registry-view both
```

Registry scopes also accept absolute PowerShell-style paths such as `HKCU:\Software` and `Registry::HKEY_CURRENT_USER\Software`, with an optional trailing backslash. Equivalent scopes are scanned once per selected view. Use backslashes as separators; names such as `.`, `..`, `a/b`, and names containing spaces or brackets are literal registry keys. Drive-relative forms such as `HKCU:Software` are rejected.

Apply cleanup by adding `--apply`. Repeat `--path` and `--registry` to combine explicit scopes:

```powershell
python -m xsunshine --path 'C:\Example' --apply
```

For system-wide discovery and cleanup:

```powershell
python -m xsunshine --all
python -m xsunshine --all --apply --trace cleanup.trace.jsonl
```

`--all` covers local fixed volumes, including volumes without drive letters, plus loaded `HKLM` and `HKU` hives in both registry views. The current user's hive is included under `HKU`; merged aliases such as `HKCR` are not scanned again. Offline user hives are not loaded. Network and removable locations can be supplied explicitly with `--path`. Use an elevated terminal when access to system-owned locations is needed; access failures are reported without changing permissions.

Empty directories and keys can still be expected by installed software. Review the preview before applying. Deletions are permanent and diagnostic logs are not backups.

## Cleanup rules

| Object | Behavior |
| --- | --- |
| Empty directory | Eligible after its removable descendants are processed. |
| Directory containing a file | Retained, including hidden and zero-byte files. Empty child directories remain eligible. |
| Empty registry key | Eligible only with zero subkeys and zero values. |
| Empty string, binary, or zero-valued registry entry | Preserved; an existing value makes its key nonempty. |
| Scope root or hive root | Retained. Overlapping scopes are reduced to the outermost root. |
| Junction, symbolic link, or other reparse point | Skipped, including links inside explicitly supplied paths. |
| Inaccessible or concurrently changed object | Reported; other branches continue. |

Directory deletion uses non-recursive `rmdir`, which refuses nonempty directories. Registry deletion rechecks emptiness under a Windows transaction and rolls back on failure; there is no nontransactional fallback. Avoid moving or replacing scanned trees while a run is in progress. Preview counts are projections and can change before apply. Shared registry branches can appear in both view previews.

If a file disappears between enumeration and inspection, traversal continues with the remaining entries and rechecks the directory before deletion. Ordinary access errors remain visible and other branches continue.

## PowerShell launcher and diagnostics

```powershell
pwsh -NoProfile -File .\xsunshine.ps1 --path 'C:\Example'
```

The launcher preserves the caller's working directory. Set `XSUNSHINE_PYTHON` to a Python executable if `python` is not on `PATH`. You can also run `python run.py` from a checkout, or install with `python -m pip install .` to use the `xsunshine` command.

`--trace FILE` writes a new JSON Lines file containing visits, decisions, errors, and a final summary. Existing files are never overwritten. `--verbose` prints visits and retained objects as well as candidates, deletions, and errors.

Live statuses use cyan for candidates, green for deletions, yellow for skips, and red for errors. Colors are automatic in supported terminals, including Windows consoles; redirected output stays plain. Use `--color always` to force colors or `--color never` to disable them. Automatic mode honors `NO_COLOR` and `TERM=dumb`. JSONL logs never include color codes.

Every scan finishes with directory and registry-view breakdowns and a combined total:

```text
Directories: visited=3 candidates=2 deleted=2 skipped=0 errors=0
Registry (64-bit): visited=2 candidates=1 deleted=1 skipped=0 errors=0
TOTAL (APPLY): visited=5 candidates=3 deleted=3 skipped=0 errors=0
```

Totals add the counters across all selected scopes. Preview totals count projected candidates; apply totals distinguish candidates from successful deletions. Interrupted or incomplete runs identify that status and retain the counts already recorded. Registry counts are per view, so shared branches can be counted in both previews. The JSONL summary includes the same breakdown in `by_kind` and a completion `status`.

A terminal or trace-write failure stops further cleanup and marks the run as failed. Completed deletions remain counted; the terminal prints partial totals when output is still available. A failed trace file may be incomplete. Reporting failures are separate from per-object access errors in the counters.

Exit codes: `0` completed without errors (intentional skips may remain), `1` incomplete due to errors, `2` invalid arguments, and `130` interrupted. Already completed deletions remain applied after an interruption.

## Repository structure

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | General contributor and agent instructions, including user requirements. |
| `xsunshine/` | Terminal interface, shared pruning engine, filesystem and registry adapters. |
| `tests/` | Standard-library unit and isolated Windows integration tests. |
| `run.py`, `xsunshine.ps1` | Checkout launchers. |
| `pyproject.toml` | Package metadata, pinned development tooling, and Ruff configuration. |
| `docs/development.md` | Architecture, tracer-bullet workflow, and API references. |
| `docs/releases/` | Versioned release notes used for GitHub release pages. |

The wiki has its own Git repository; see the [development guide](https://github.com/glitchykid/xsunshine/wiki/Development).

## Development and validation

Follow [AGENTS.md](AGENTS.md). Use TDD and tracer-bullet development: deliver a working path from terminal input through the Windows adapter to observable results, then extend it with tested behavior.

```powershell
python -m unittest discover -s tests -v
python -m pip install --group dev
python -m ruff check .
python -m ruff format --check .
python -m pip wheel . --no-deps --wheel-dir dist
git diff --check
```

Tests create temporary directories and uniquely named keys under `HKCU\Software\XSunshine.Tests.<uuid>`, then remove those fixtures. They never invoke system-wide deletion. The suite covers recursive previews and deletion, retained values/files, deep trees, links, races, rollback, argument validation, and the PowerShell launcher. There is no numerical coverage threshold; every changed behavior requires relevant tests.

## Releases

[v0.3.1](docs/releases/v0.3.1.md) improves registry path handling and reliability during filesystem changes or reporting failures. [v0.3.0](docs/releases/v0.3.0.md) added live colors and final totals. See [published releases](https://github.com/glitchykid/xsunshine/releases) and the [wiki](https://github.com/glitchykid/xsunshine/wiki) for usage and publishing guidance.
