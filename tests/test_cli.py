import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from xsunshine import __version__
from xsunshine.cli import fixed_drives, main


class CommandTests(unittest.TestCase):
    def test_broken_stdout_preserves_trace_summary_and_prints_plain_totals_to_stderr(self):
        class BrokenOutput(io.StringIO):
            failed = False

            def write(self, text):
                if "DELETED" in text:
                    self.failed = True
                if self.failed:
                    raise BrokenPipeError("Output pipe closed")
                return super().write(text)

        trace = self.root / "broken-output.jsonl"
        errors = io.StringIO()
        with redirect_stdout(BrokenOutput()), redirect_stderr(errors):
            code = main(
                [
                    "--path",
                    str(self.scope),
                    "--apply",
                    "--trace",
                    str(trace),
                    "--color",
                    "always",
                ]
            )
        self.assertEqual(code, 1)
        self.assertTrue((self.scope / "parent").exists())
        self.assertFalse((self.scope / "parent" / "leaf").exists())
        self.assertIn("TOTAL (APPLY, failed): visited=3 candidates=1 deleted=1", errors.getvalue())
        self.assertNotIn("\x1b", errors.getvalue())
        summary = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["deleted"], 1)

    def test_total_output_failure_keeps_failed_summary_in_trace(self):
        class BrokenOutput(io.StringIO):
            def write(self, text):
                if "TOTAL" in text:
                    raise BrokenPipeError("Output pipe closed")
                return super().write(text)

        trace = self.root / "broken-total.jsonl"
        errors = io.StringIO()
        with redirect_stdout(BrokenOutput()), redirect_stderr(errors):
            code = main(["--path", str(self.scope), "--trace", str(trace)])
        self.assertEqual(code, 1)
        self.assertIn("TOTAL (PREVIEW, failed):", errors.getvalue())
        summary = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["candidates"], 2)

    def test_command_with_closed_output_pipe_exits_cleanly_with_partial_totals(self):
        launcher = Path(__file__).resolve().parents[1] / "run.py"
        for index, command in enumerate((["-m", "xsunshine"], [str(launcher)])):
            with self.subTest(command=command):
                trace = self.root / f"closed-pipe-{index}.jsonl"
                read_fd, write_fd = os.pipe()
                os.close(read_fd)
                try:
                    process = subprocess.run(
                        [
                            sys.executable,
                            *command,
                            "--path",
                            str(self.scope),
                            "--apply",
                            "--trace",
                            str(trace),
                        ],
                        stdout=write_fd,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=30,
                    )
                finally:
                    os.close(write_fd)
                self.assertEqual(process.returncode, 1, process.stderr)
                self.assertNotIn("Exception ignored", process.stderr)
                self.assertIn("TOTAL (APPLY, failed):", process.stderr)
                summary = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual(summary["status"], "failed")
                self.assertTrue((self.scope / "parent" / "leaf").exists())

    def test_final_trace_failure_reports_failed_totals(self):
        class FailingSummary(io.StringIO):
            def write(self, text):
                if json.loads(text)["action"] == "summary":
                    raise OSError("Trace disk is full")
                return super().write(text)

        with patch("xsunshine.cli.Path.open", return_value=FailingSummary()):
            code, output, errors = self.invoke("--path", str(self.scope), "--trace", "test.jsonl")
        self.assertEqual(code, 1)
        self.assertIn("Trace disk is full", errors)
        self.assertIn("TOTAL (PREVIEW, failed): visited=3 candidates=2", errors)

    def test_unavailable_terminal_streams_still_write_zero_progress_to_trace(self):
        for failure in (BrokenPipeError("Closed pipe"), ValueError("Closed stream")):
            with self.subTest(failure=type(failure).__name__):
                trace = self.root / (type(failure).__name__ + ".jsonl")
                with (
                    patch("sys.stdout.write", side_effect=failure),
                    patch("sys.stderr.write", side_effect=failure),
                ):
                    code = main(["--path", str(self.scope), "--apply", "--trace", str(trace)])
                self.assertEqual(code, 1)
                self.assertTrue((self.scope / "parent" / "leaf").exists())
                summary = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual(summary["status"], "failed")
                self.assertEqual(summary["visited"], 0)
                self.assertEqual(summary["deleted"], 0)

    def test_total_flush_failure_reports_failed_status_to_remaining_channels(self):
        class FailedFlush(io.StringIO):
            def flush(self):
                if "TOTAL" in self.getvalue():
                    raise OSError("Cannot flush output")

        trace = self.root / "flush.jsonl"
        errors = io.StringIO()
        with redirect_stdout(FailedFlush()), redirect_stderr(errors):
            code = main(["--path", str(self.scope), "--trace", str(trace)])
        self.assertEqual(code, 1)
        self.assertIn("TOTAL (PREVIEW, failed):", errors.getvalue())
        summary = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["candidates"], 2)

    def test_persistent_trace_failure_preserves_partial_totals(self):
        class FullTrace(io.StringIO):
            failed = False

            def write(self, text):
                if json.loads(text)["action"] == "deleted":
                    self.failed = True
                if self.failed:
                    raise OSError("Trace disk is full")
                return super().write(text)

        with patch("xsunshine.cli.Path.open", return_value=FullTrace()):
            code, output, errors = self.invoke(
                "--path", str(self.scope), "--apply", "--trace", "test.jsonl"
            )
        self.assertEqual(code, 1)
        self.assertTrue((self.scope / "parent").exists())
        self.assertFalse((self.scope / "parent" / "leaf").exists())
        for stream in (output, errors):
            self.assertIn("TOTAL (APPLY, failed): visited=3 candidates=1 deleted=1", stream)

    def test_trace_write_failure_stops_before_later_deletions_and_reports_totals(self):
        class FailingTrace(io.StringIO):
            failed = False

            def write(self, text):
                event = json.loads(text)
                if (
                    not self.failed
                    and event["action"] == "visit"
                    and event["path"].endswith("leaf")
                ):
                    self.failed = True
                    raise OSError("Trace disk is full")
                return super().write(text)

            def close(self):
                self.saved = self.getvalue()
                super().close()

        sibling = self.scope / "zz-other"
        sibling.mkdir()
        trace = FailingTrace()
        with patch("xsunshine.cli.Path.open", return_value=trace):
            code, output, errors = self.invoke(
                "--path", str(self.scope), "--apply", "--trace", "test.jsonl"
            )
        self.assertEqual(code, 1)
        self.assertTrue(sibling.exists())
        self.assertIn("Trace disk is full", errors)
        self.assertIn("TOTAL (APPLY, failed):", output)
        summary = json.loads(trace.saved.splitlines()[-1])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["deleted"], 0)
        self.assertEqual(summary["errors"], 0)

    def test_powershell_registry_aliases_are_deduplicated_before_scanning(self):
        from xsunshine.core import Snapshot

        class RegistryFixture:
            def __init__(self, root, view):
                self.root, self.kind = root, "registry" + view

            def inspect(self, node):
                return Snapshot((), False)

        with patch("xsunshine.cli.RegistryTree", side_effect=RegistryFixture) as factory:
            code, _, _ = self.invoke(
                "--registry",
                "HKCU:\\Software\\",
                "--registry",
                r"Registry::HKEY_CURRENT_USER\Software",
                "--registry-view",
                "64",
            )
        self.assertEqual(code, 0)
        factory.assert_called_once_with(r"HKCU\Software", "64")

    def setUp(self):
        fixture = tempfile.TemporaryDirectory(prefix="xsunshine-cli-")
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.scope = self.root / "scope"
        (self.scope / "parent" / "leaf").mkdir(parents=True)

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            result = main(list(args))
        return result, output.getvalue(), errors.getvalue()

    def test_default_is_preview(self):
        code, output, _ = self.invoke("--path", str(self.scope))
        self.assertEqual(code, 0)
        self.assertIn("PREVIEW", output)
        self.assertIn("candidates=2", output)
        self.assertTrue((self.scope / "parent" / "leaf").exists())

    def test_explicit_apply_deletes_recursively(self):
        code, output, _ = self.invoke("--path", str(self.scope), "--apply")
        self.assertEqual(code, 0)
        self.assertIn("deleted=2", output)
        self.assertEqual(list(self.scope.iterdir()), [])

    def test_missing_path_returns_failure(self):
        code, output, _ = self.invoke("--path", str(self.root / "missing"))
        self.assertEqual(code, 1)
        self.assertIn("errors=1", output)

    def test_overlapping_paths_are_scanned_once(self):
        code, output, _ = self.invoke(
            "--path", str(self.scope / "parent"), "--path", str(self.scope)
        )
        self.assertEqual(code, 0)
        self.assertIn("candidates=2", output)

    def test_trace_contains_visits_candidates_and_summary(self):
        trace = self.root / "events.jsonl"
        code, _, _ = self.invoke("--path", str(self.scope), "--trace", str(trace))
        self.assertEqual(code, 0)
        records = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[0]["action"], "start")
        self.assertIn("visit", [record["action"] for record in records])
        self.assertEqual(records[-1]["action"], "summary")
        self.assertEqual(records[-1]["candidates"], 2)

    def test_existing_trace_is_not_overwritten_and_no_deletions_occur(self):
        trace = self.root / "events.jsonl"
        trace.write_text("keep", encoding="utf-8")
        code, _, _ = self.invoke("--path", str(self.scope), "--apply", "--trace", str(trace))
        self.assertEqual(code, 1)
        self.assertEqual(trace.read_text(encoding="utf-8"), "keep")
        self.assertTrue((self.scope / "parent" / "leaf").exists())

    def test_no_scope_and_invalid_registry_are_usage_errors(self):
        for args in [
            [],
            ["--registry", "BAD"],
            ["--registry", "HKCU", "--registry-view", "16"],
            ["--all", "--path", str(self.scope)],
        ]:
            with (
                self.subTest(args=args),
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                main(args)
            self.assertEqual(error.exception.code, 2)

    def test_version_needs_no_scope(self):
        with redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as error:
            main(["--version"])
        self.assertEqual(error.exception.code, 0)
        self.assertIn(__version__, output.getvalue())

    def test_all_selects_fixed_drives_and_loaded_hives_in_both_views(self):
        class EmptyTree:
            def __init__(self, root, view):
                self.root = root
                self.kind = "registry" + view

        from xsunshine.core import Result

        with (
            patch("xsunshine.cli.fixed_drives", return_value=[str(self.scope)]),
            patch("xsunshine.cli.RegistryTree", side_effect=EmptyTree) as registry,
            patch("xsunshine.cli.prune", return_value=Result()) as scanner,
        ):
            code, _, _ = self.invoke("--all")
        self.assertEqual(code, 0)
        self.assertEqual(scanner.call_count, 5)
        self.assertEqual(
            {call.args for call in registry.call_args_list},
            {("HKLM", "32"), ("HKLM", "64"), ("HKU", "32"), ("HKU", "64")},
        )

    def test_interrupt_returns_130(self):
        with patch("xsunshine.cli.prune", side_effect=KeyboardInterrupt):
            self.assertEqual(self.invoke("--path", str(self.scope))[0], 130)

    def test_final_total_combines_scopes_and_shows_directory_breakdown(self):
        second = self.root / "second"
        (second / "empty").mkdir(parents=True)
        code, output, _ = self.invoke("--path", str(self.scope), "--path", str(second))
        self.assertEqual(code, 0)
        self.assertIn("Directories: visited=5 candidates=3 deleted=0 skipped=0 errors=0", output)
        self.assertEqual(
            output.splitlines()[-1],
            "TOTAL (PREVIEW): visited=5 candidates=3 deleted=0 skipped=0 errors=0",
        )

    def test_empty_scope_still_prints_zero_total(self):
        empty = self.root / "empty"
        empty.mkdir()
        _, output, _ = self.invoke("--path", str(empty))
        self.assertIn("TOTAL (PREVIEW): visited=1 candidates=0 deleted=0", output)

    def test_total_includes_both_registry_views_and_directories(self):
        from xsunshine.core import Snapshot

        class RegistryFixture:
            def __init__(self, root, view):
                self.root, self.kind = root, "registry" + view

            def inspect(self, node):
                return Snapshot((self.root + r"\empty",) if node == self.root else (), False)

        with patch("xsunshine.cli.RegistryTree", side_effect=RegistryFixture):
            code, output, _ = self.invoke("--path", str(self.scope), "--registry", r"HKCU\Fixture")
        self.assertEqual(code, 0)
        self.assertIn("Registry (32-bit): visited=2 candidates=1", output)
        self.assertIn("Registry (64-bit): visited=2 candidates=1", output)
        self.assertIn("TOTAL (PREVIEW): visited=7 candidates=4 deleted=0", output)

    def test_interrupted_scope_reports_work_already_completed(self):
        def interrupted(tree, root, *, result, **kwargs):
            result.visited = 3
            result.candidates = 2
            result.deleted = 1
            raise KeyboardInterrupt

        trace = self.root / "interrupted.jsonl"
        with patch("xsunshine.cli.prune", side_effect=interrupted):
            code, output, _ = self.invoke(
                "--path", str(self.scope), "--apply", "--trace", str(trace)
            )
        self.assertEqual(code, 130)
        self.assertIn("TOTAL (APPLY, interrupted): visited=3 candidates=2 deleted=1", output)
        summary = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(summary["status"], "interrupted")
        self.assertEqual(summary["deleted"], 1)

    def test_forced_colors_do_not_leak_into_trace(self):
        trace = self.root / "colors.jsonl"
        code, output, _ = self.invoke(
            "--path", str(self.scope), "--color", "always", "--trace", str(trace)
        )
        self.assertEqual(code, 0)
        self.assertIn("\x1b[36mCANDIDATE\x1b[0m", output)
        self.assertIn("\x1b[", output.splitlines()[-1])
        self.assertNotIn("\x1b", trace.read_text(encoding="utf-8"))
        self.assertNotIn("\\u001b", trace.read_text(encoding="utf-8"))

    def test_redirected_output_and_never_mode_are_plain(self):
        for flags in [[], ["--color", "never"]]:
            with self.subTest(flags=flags):
                _, output, _ = self.invoke("--path", str(self.scope), *flags)
                self.assertNotIn("\x1b", output)

    @unittest.skipUnless(os.name == "nt", "Windows volume discovery")
    def test_system_discovery_includes_volumes_without_drive_letters_once(self):
        from unittest.mock import Mock

        drive_type = Mock(return_value=3)
        native = Mock(GetDriveTypeW=drive_type)
        mounts = {"volume-c": ["C:\\"], "volume-mounted": ["C:\\mount\\"], "volume-hidden": []}
        with (
            patch("xsunshine.cli.ctypes.WinDLL", return_value=native),
            patch("xsunshine.cli.os.listdrives", return_value=["C:\\"]),
            patch("xsunshine.cli.os.listvolumes", return_value=list(mounts)),
            patch("xsunshine.cli.os.listmounts", side_effect=mounts.__getitem__),
        ):
            self.assertEqual(fixed_drives(), ["C:\\", "volume-mounted", "volume-hidden"])

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 launcher integration")
    def test_powershell_launcher_preserves_caller_directory_and_arguments(self):
        launcher = Path(__file__).resolve().parents[1] / "xsunshine.ps1"
        environment = {**os.environ, "XSUNSHINE_PYTHON": sys.executable}
        process = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(launcher), "--path", "scope", "--apply"],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn("deleted=2", process.stdout)
        self.assertEqual(list(self.scope.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
