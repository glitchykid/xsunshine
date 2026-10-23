import ctypes
import os
import unittest
import uuid
from unittest.mock import patch

if os.name == "nt":
    import winreg

from xsunshine.core import prune
from xsunshine.registry import RegistryTree, normalize_registry_path


def remove_test_link(path, view):
    """Remove the link itself, without resolving its target, during test cleanup."""
    import re
    from ctypes import wintypes

    if not re.fullmatch(r"Software\\XSunshine\.Tests\.[0-9a-f]{32}\\link", path):
        raise ValueError("Not a test registry link")
    from xsunshine.registry import RegistryAPI

    api = RegistryAPI()
    handle = wintypes.HANDLE()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software", 0, winreg.KEY_READ | view) as parent:
        error = api.open(
            int(parent),
            path.removeprefix("Software\\"),
            8,
            winreg.KEY_READ | 0x10000 | view,
            ctypes.byref(handle),
        )
    if error:
        raise ctypes.WinError(error)
    try:
        delete = ctypes.WinDLL("ntdll").NtDeleteKey
        delete.argtypes = [wintypes.HANDLE]
        delete.restype = wintypes.LONG
        status = delete(handle)
        if status:
            raise OSError(f"Test link cleanup failed: NTSTATUS {status:#x}")
    finally:
        winreg.CloseKey(handle.value)


class RegistryPathTests(unittest.TestCase):
    def test_hive_aliases_are_normalized(self):
        self.assertEqual(normalize_registry_path(r"HKEY_CURRENT_USER\Software"), r"HKCU\Software")
        self.assertEqual(normalize_registry_path("hklm"), "HKLM")

    def test_invalid_paths_are_rejected(self):
        for value in [
            "",
            "C:\\",
            "HKBOGUS",
            "HKCU:Software",
            "HKCU:",
            "HKCU\\\\Software",
            "HKCU\x00",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_registry_path(value)

    def test_absolute_powershell_paths_and_trailing_separators_are_normalized(self):
        for value in [
            "HKCU:\\Software\\",
            r"Registry::HKEY_CURRENT_USER\Software",
            r"registry::hkey_current_user\Software",
            "HKCU\\Software\\",
        ]:
            with self.subTest(value=value):
                self.assertEqual(normalize_registry_path(value), r"HKCU\Software")
        self.assertEqual(normalize_registry_path("HKLM:\\"), "HKLM")

    def test_printable_key_names_are_literal(self):
        for name in [".", "..", "a/b", " spaced [name] "]:
            path = "HKCU\\Software\\" + name
            with self.subTest(name=name):
                self.assertEqual(normalize_registry_path(path), path)


@unittest.skipUnless(os.name == "nt", "Windows registry integration")
class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.key_path = "Software\\XSunshine.Tests." + uuid.uuid4().hex
        self.root = "HKCU\\" + self.key_path
        self.view = winreg.KEY_WOW64_64KEY
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_ALL_ACCESS | self.view
        ):
            pass
        self.addCleanup(self.remove_fixture)
        self.tree = RegistryTree(self.root, "64")

    def remove_fixture(self):
        # Delete only the uniquely named branch created by this test.
        self.assertRegex(self.key_path, r"^Software\\XSunshine\.Tests\.[0-9a-f]{32}$")

        def remove(path):
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | self.view
            ) as key:
                children = [winreg.EnumKey(key, i) for i in range(winreg.QueryInfoKey(key)[0])]
            for name in children:
                remove(path + "\\" + name)
            winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, path, self.view)

        remove(self.key_path)

    def make(self, relative, value=None, name="", kind=None):
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            self.key_path + "\\" + relative,
            0,
            winreg.KEY_ALL_ACCESS | self.view,
        ) as key:
            if value is not None:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ if kind is None else kind, value)

    def exists(self, relative):
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.key_path + "\\" + relative,
                0,
                winreg.KEY_READ | self.view,
            ):
                return True
        except FileNotFoundError:
            return False

    def test_recursive_delete_removes_newly_empty_parents(self):
        self.make(r"parent\child\leaf")
        result = prune(self.tree, self.root, apply=True)
        self.assertEqual(result.errors, 0)
        self.assertEqual(result.deleted, 3)
        self.assertFalse(self.exists("parent"))

    def test_literal_dot_slash_and_spaced_keys_do_not_abort_cleanup(self):
        names = [".", "..", "a/b", " spaced [name] "]
        for name in names:
            self.make(name + r"\leaf")
        self.make("keep", "value")
        result = prune(self.tree, self.root, apply=True)
        self.assertEqual(result.deleted, 8)
        self.assertEqual(result.errors, 0)
        self.assertTrue(self.exists("keep"))

    def test_powershell_scope_cannot_escape_literal_dot_key(self):
        self.make("..")
        self.make(r"sibling\empty")
        root = "HKCU:\\" + self.key_path + "\\..\\"
        tree = RegistryTree(root, "64")
        result = prune(tree, tree.root, apply=True)
        self.assertEqual(result.deleted, 0)
        self.assertTrue(self.exists(r"sibling\empty"))

    def test_preview_preserves_keys(self):
        self.make(r"parent\leaf")
        result = prune(self.tree, self.root)
        self.assertEqual(result.candidates, 2)
        self.assertTrue(self.exists(r"parent\leaf"))

    def test_empty_default_zero_and_binary_values_are_not_empty_keys(self):
        self.make("default", "")
        self.make("number", 0, kind=winreg.REG_DWORD)
        self.make("binary", b"", kind=winreg.REG_BINARY)
        self.make("empty")
        result = prune(self.tree, self.root, apply=True)
        self.assertEqual(result.deleted, 1)
        for key in ["default", "number", "binary"]:
            self.assertTrue(self.exists(key))

    def test_empty_children_of_valued_keys_are_removed(self):
        self.make("parent", "keep")
        self.make(r"parent\empty")
        self.assertEqual(prune(self.tree, self.root, apply=True).deleted, 1)
        self.assertTrue(self.exists("parent"))

    def test_value_added_after_scan_prevents_deletion(self):
        self.make("changing")
        self.make("changing", "arrived")
        self.assertFalse(self.tree.remove_empty(self.root + r"\changing", None))
        self.assertTrue(self.exists("changing"))

    def test_existing_value_matching_internal_marker_is_preserved(self):
        marker_id = uuid.UUID(int=1)
        self.make("changing", "keep", name="XSunshine.Transaction." + marker_id.hex)
        with patch("xsunshine.registry.uuid.uuid4", return_value=marker_id):
            removed = self.tree.remove_empty(self.root + r"\changing", None)
        self.assertFalse(removed)
        self.assertTrue(self.exists("changing"))

    def test_failed_commit_rolls_back_without_nontransactional_fallback(self):
        self.make("empty")
        with patch.object(self.tree.api, "commit", return_value=0):
            result = prune(self.tree, self.root, apply=True)
        self.assertEqual(result.errors, 1)
        self.assertEqual(result.deleted, 0)
        self.assertTrue(self.exists("empty"))

    def test_scope_root_and_outside_keys_are_protected(self):
        for node in [self.root, "HKCU\\Software"]:
            with self.subTest(node=node), self.assertRaises(ValueError):
                self.tree.remove_empty(node, None)

    def test_explicit_32_bit_view_is_supported(self):
        tree = RegistryTree(self.root, "32")
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            self.key_path + r"\view32",
            0,
            winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_32KEY,
        ):
            pass
        result = prune(tree, self.root, apply=True)
        self.assertEqual(result.errors, 0)
        self.assertEqual(result.deleted, 1)

    def test_missing_key_reports_error(self):
        missing = self.root + r"\absent"
        self.assertEqual(prune(RegistryTree(missing, "64"), missing).errors, 1)

    def test_transaction_marker_is_invisible_to_other_handles(self):
        self.make("empty")
        real_set_value = winreg.SetValueEx
        checked = []

        def check_marker(key, name, *args):
            real_set_value(key, name, *args)
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.key_path + r"\empty", 0, winreg.KEY_READ | self.view
            ) as outside:
                self.assertEqual(winreg.QueryInfoKey(outside)[1], 0)
            checked.append(True)

        with patch("xsunshine.registry.winreg.SetValueEx", side_effect=check_marker):
            result = prune(self.tree, self.root, apply=True)
        self.assertEqual(result.deleted, 1)
        self.assertTrue(checked)

    def test_registry_links_are_skipped_including_explicit_scopes(self):
        from ctypes import wintypes

        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        create = advapi.RegCreateKeyExW
        create.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.HANDLE),
            ctypes.POINTER(wintypes.DWORD),
        ]
        create.restype = wintypes.LONG
        link_path = self.key_path + r"\link"
        handle, disposition = wintypes.HANDLE(), wintypes.DWORD()
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_ALL_ACCESS | self.view
        ) as parent:
            error = create(
                int(parent),
                "link",
                0,
                None,
                2,
                winreg.KEY_ALL_ACCESS | self.view,
                None,
                ctypes.byref(handle),
                ctypes.byref(disposition),
            )
        if error in (5, 1314):
            self.skipTest("Creating registry links is not permitted for this account")
        self.assertEqual(error, 0)
        self.addCleanup(remove_test_link, link_path, self.view)
        try:
            winreg.SetValueEx(
                handle.value,
                "SymbolicLinkValue",
                0,
                winreg.REG_LINK,
                r"\Registry\User\XSunshine.Tests.Nonexistent".encode("utf-16-le"),
            )
        finally:
            winreg.CloseKey(handle.value)
        result = prune(self.tree, self.root, apply=True)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.deleted, 0)
        explicit = self.root + r"\link\child"
        result = prune(RegistryTree(explicit, "64"), explicit, apply=True)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.errors, 0)

    def test_concurrent_value_write_cannot_silently_lose_data(self):
        self.make("changing")
        actual_delete = self.tree.api.delete
        written = []

        def race(*args):
            try:
                self.make("changing", "concurrent value")
                written.append(True)
            except OSError as exc:
                self.assertIn(exc.winerror, (6800, 6801))
            return actual_delete(*args)

        with patch.object(self.tree.api, "delete", side_effect=race):
            result = prune(self.tree, self.root, apply=True)
        if written:
            self.assertEqual(result.deleted, 0)
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.key_path + r"\changing",
                0,
                winreg.KEY_READ | self.view,
            ) as key:
                self.assertEqual(winreg.QueryValueEx(key, "")[0], "concurrent value")
        else:
            self.assertEqual(result.deleted + result.errors, 1)


if __name__ == "__main__":
    unittest.main()
