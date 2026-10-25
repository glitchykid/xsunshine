# Development

## Architecture and language choice

Python provides filesystem iteration, `winreg`, argument parsing, packaging, and a test runner without third-party runtime dependencies. Small `ctypes` bindings expose Windows registry transactions and volume classification. A PowerShell launcher keeps Windows terminal usage familiar without implementing a second cleanup engine. This gives a smaller maintenance surface than implementing the application and its test infrastructure in C.

The current versions are Python 3.15.1, PowerShell 7.6.8, Ruff 0.17.2, and setuptools 84.2.1. Check their official stable releases and version-specific documentation when updating dependencies.

`cli.py` selects scopes and reports events. `core.py` performs iterative post-order traversal through a small `Tree` protocol. `filesystem.py` and `registry.py` define emptiness and perform non-recursive deletion. Preview simulates removed descendants; apply rechecks objects before removal. Scope roots remain traversal boundaries.

Registry path normalization accepts absolute hive and PowerShell provider syntax without treating key names as filesystem paths. Dot and slash names remain literal. Filesystem enumeration tolerates entries that disappear before inspection; final emptiness checks remain authoritative. The engine distinguishes reporting failures from per-object access errors: reporting failures propagate immediately to stop cleanup, while progress already recorded remains available to the terminal summary.

Final reporting attempts terminal output and the trace independently. Standard error receives plain fallback totals if either fails, including a corrected failed status when the final trace write fails. The process entry point flushes standard streams and redirects a failed stream to the null device before interpreter shutdown, preserving the application's exit status. Subprocess tests use an already-closed pipe receiver to verify this behavior without a timing race.

Registry deletion uses a short transaction per candidate. A private temporary value acquires the write lock, is removed, and then emptiness is checked again before deletion commits. The initial emptiness check preserves any existing values, including names resembling the internal marker. Failure rolls back; extra write permissions and Windows transaction support are required. The test suite verifies the marker is invisible to other handles and that competing writes cannot silently lose a value in the tested race.

## Tracer-bullet development and TDD

The methodology is the tracer-bullet approach from *The Pragmatic Programmer*, not diagnostic logging. Build a small working implementation through the real layers, validate observable behavior, and refine it with feedback. Keep the resulting code as the application foundation.

For this milestone, the working path is terminal arguments → scope selection → recursive cleanup → Windows filesystem/registry → terminal result. Tests were introduced before the corresponding implementation, including an observed failing concurrent-write case that drove the transaction design. Extend this path incrementally rather than adding unused abstractions.

Run the commands in the [README](../README.md). Destructive integration tests must remain inside their generated temporary folders and registry branches. System-wide deletion is a user-invoked operation, not a development test. The `--trace` option is a separate diagnostic feature.

## References consulted

- [Python 3.15 broken-pipe handling](https://docs.python.org/3.15/library/signal.html#note-on-sigpipe) and [shutdown exit status](https://docs.python.org/3.15/library/sys.html#sys.exit).
- [Python 3.15 filesystem APIs](https://docs.python.org/3.15/library/os.html), [registry APIs](https://docs.python.org/3.15/library/winreg.html), [ctypes](https://docs.python.org/3.15/library/ctypes.html), [argparse](https://docs.python.org/3.15/library/argparse.html), and [unittest](https://docs.python.org/3.15/library/unittest.html).
- [RegOpenKeyExW](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-regopenkeyexw), [RegOpenKeyTransactedW](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-regopenkeytransactedw), [RegDeleteKeyTransactedW](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-regdeletekeytransactedw), and [CreateTransaction](https://learn.microsoft.com/en-us/windows/win32/api/ktmw32/nf-ktmw32-createtransaction).
- [PowerShell 7.6 automatic variables](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_automatic_variables?view=powershell-7.6).
- [Windows registry key naming](https://learn.microsoft.com/en-us/windows/win32/sysinfo/structure-of-the-registry) and [PowerShell registry provider paths](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_registry_provider?view=powershell-7.6).
- [Ruff configuration](https://docs.astral.sh/ruff/configuration/) and [setuptools package configuration](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html).
- [The Pragmatic Programmer authors' tips](https://books.pragprog.com/tips/), including tracer bullets.
